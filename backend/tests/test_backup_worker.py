"""Encrypted production-backup worker contracts with synthetic PostgreSQL data.

No production database, cloud secrets or real Supabase bucket is used here.
The real pg_dump/AES-GCM restore integration is separately covered by the
S4P encrypted backup and restore drill workflow.
"""
import hashlib
import json
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.services import backup_worker


class FakeBridge:
    def __init__(self, *, previous=None):
        self.objects = {}
        self.previous = previous

    def _request(self, op, *, name="", data=b"", mime=""):
        if op == "health":
            return b'{"ok":true,"private":true}'
        if op == "status":
            if self.previous:
                return json.dumps({"available": True, **self.previous}).encode()
            return b'{"available":false}'
        if op == "upload":
            if name in self.objects:
                raise AssertionError("Backup chunks are immutable")
            self.objects[name] = data
            return b'{"ok":true}'
        if op == "download":
            return self.objects[name]
        if op == "publish":
            self.previous = json.loads(data)
            assert self.previous["manifestKey"] in self.objects
            return b'{"ok":true}'
        raise AssertionError(f"unexpected operation {op}")


def test_first_backup_is_due_and_recent_backup_is_skipped():
    now = datetime.now(timezone.utc)
    fresh = FakeBridge(previous={"manifestKey": "some-key", "createdAt": now.strftime("%Y-%m-%dT%H:%M:%SZ")})
    assert not backup_worker.backup_due(fresh, now=now)
    old = FakeBridge(previous={
        "manifestKey": "some-key",
        "createdAt": (now - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })
    assert backup_worker.backup_due(old, now=now)
    assert backup_worker.backup_due(FakeBridge(), now=now)


def test_signed_remote_backup_creates_verified_immutable_chunks(monkeypatch):
    bridge = FakeBridge()
    monkeypatch.setattr(backup_worker, "_bridge", lambda: bridge)

    fake_backup = types.ModuleType("s4p_backup")
    fake_backup.key_bytes = lambda: b"k" * 32
    fake_backup.db_environment = lambda dsn: ({"PGHOST": "test"}, ("test", 5432, "fake"))

    def fake_encrypt(source: Path, target: Path, key):
        assert key == b"k" * 32
        target.write_bytes(b"encrypted snapshot " * 200_000)
    fake_backup.encrypt_file = fake_encrypt
    monkeypatch.setitem(sys.modules, "s4p_backup", fake_backup)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://test:example@host/test")
    monkeypatch.setattr(backup_worker.secrets, "token_hex", lambda n: "c" * (n * 2))

    def fake_dump(args, **kwargs):
        assert args[0] == "pg_dump"
        assert kwargs["timeout"] == 180
        Path(args[-1]).write_bytes(b"FAKE_POSTGRES_DUMP")
    monkeypatch.setattr(backup_worker.subprocess, "run", fake_dump)

    result = backup_worker.create_encrypted_backup()
    assert result["skipped"] is False
    assert result["chunks"] == 2
    assert result["encryptedBytes"] > 3 * 1024 * 1024

    pointer = bridge.previous
    assert pointer["manifestKey"].endswith("/manifest.json")
    manifest = json.loads(bridge.objects[pointer["manifestKey"]])
    assert len(manifest["parts"]) == 2
    assert manifest["format"] == "s4p-aes256-gcm-parts-v1"
    for part in manifest["parts"]:
        assert part["bytes"] == len(bridge.objects[part["key"]])
        assert len(part["sha256"]) == 64
    again = backup_worker.create_encrypted_backup()
    assert again == {"skipped": True}


def test_status_rejects_corrupt_timestamp():
    bridge = FakeBridge(previous={"manifestKey": "some-key", "createdAt": "invalid"})
    with pytest.raises(RuntimeError, match="timestamp"):
        backup_worker.backup_due(bridge)


def test_verify_latest_offsite_snapshot_authenticates_and_checks_pg_archive(monkeypatch):
    bridge = FakeBridge()
    monkeypatch.setattr(backup_worker, "_bridge", lambda: bridge)
    prefix = "db-backups/20261029/" + "e" * 32 + "/"
    chunk = b"ENCRYPTED_SYNTHETIC_CHUNK"
    part = prefix + "part-0001.bin"
    manifest_key = prefix + "manifest.json"
    manifest = {
        "format": "s4p-aes256-gcm-parts-v1",
        "parts": [{"key": part, "sha256": hashlib.sha256(chunk).hexdigest(), "bytes": len(chunk)}],
        "encryptedBytes": len(chunk),
        "encryptedSHA256": hashlib.sha256(chunk).hexdigest(),
    }
    bridge.objects[part] = chunk
    bridge.objects[manifest_key] = json.dumps(manifest).encode()
    bridge.previous = {"manifestKey": manifest_key, "createdAt": "2026-10-29T05:00:00Z"}

    fake_backup = types.ModuleType("s4p_backup")
    fake_backup.key_bytes = lambda: b"k" * 32

    def decrypt(src, dst, key):
        assert src.read_bytes() == chunk
        assert key == b"k" * 32
        dst.write_bytes(b"PG_CUSTOM_ARCHIVE")
    fake_backup.decrypt_file = decrypt
    monkeypatch.setitem(sys.modules, "s4p_backup", fake_backup)

    def fake_restore(args, **kwargs):
        assert args[:2] == ["pg_restore", "--list"]
        assert Path(args[2]).read_bytes() == b"PG_CUSTOM_ARCHIVE"
        assert kwargs["timeout"] == 120
    monkeypatch.setattr(backup_worker.subprocess, "run", fake_restore)
    assert backup_worker.verify_latest_encrypted_backup() is True

    bridge.objects[part] = b"CORRUPT"
    with pytest.raises(RuntimeError, match="checksum"):
        backup_worker.verify_latest_encrypted_backup()
