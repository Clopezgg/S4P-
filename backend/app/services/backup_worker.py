"""Encrypted offsite database snapshot using a signed Supabase Edge bridge.

Backup data is encrypted on Render with AES-256-GCM before any upload.
The Supabase service-role key and storage endpoint remain Supabase-side.
This module NEVER restores into the live database.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import pathlib
import secrets
import subprocess
import tempfile
from datetime import datetime, timezone

from app.core.config import get_settings
from app.integrations.supabase_edge_storage import SupabaseEdgeEvidenceContainer

logger = logging.getLogger("s4p.backup")
CHUNK_BYTES = 3 * 1024 * 1024
MIN_INTERVAL_SECONDS = 23 * 3600


def _bridge() -> SupabaseEdgeEvidenceContainer:
    settings = get_settings()
    if settings.evidence_backend != "supabase_edge":
        raise RuntimeError("Signed private Supabase storage must be enabled")
    client = SupabaseEdgeEvidenceContainer(settings)
    source = settings.supabase_edge_bridge_url.rstrip("/")
    if not source.endswith("/s4p-evidence-bridge"):
        raise RuntimeError("Unexpected Supabase Edge function URL")
    client.endpoint = source.removesuffix("s4p-evidence-bridge") + "s4p-db-backup-bridge"
    return client


def _json_call(bridge: SupabaseEdgeEvidenceContainer, op: str, *,
               key: str = "", data: bytes = b"", mime: str = "") -> dict:
    result = json.loads(bridge._request(op, name=key, data=data, mime=mime))
    if not isinstance(result, dict):
        raise RuntimeError("Backup bridge returned invalid data")
    return result


def backup_due(bridge: SupabaseEdgeEvidenceContainer, *, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    value = _json_call(bridge, "status")
    if not value.get("available"):
        return True
    raw_time = value.get("createdAt")
    if not isinstance(raw_time, str):
        raise RuntimeError("Backup status lacks a timestamp")
    try:
        previous = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeError("Invalid remote backup timestamp") from exc
    return (now - previous).total_seconds() >= MIN_INTERVAL_SECONDS


def create_encrypted_backup() -> dict:
    """Take a PostgreSQL dump, encrypt, upload immutable chunks and publish index.

    Never log DSNs, signing secrets, database bytes or encryption keys.
    An incomplete upload has no published index, so it cannot be mistaken for
    a usable snapshot.
    """
    import s4p_backup

    bridge = _bridge()
    health = _json_call(bridge, "health")
    if health.get("private") is not True or health.get("ok") is not True:
        raise RuntimeError("Private backup bucket unavailable")
    now = datetime.now(timezone.utc)
    if not backup_due(bridge, now=now):
        logger.info("Offsite backup is recent; no new snapshot required")
        return {"skipped": True}

    encryption_key = s4p_backup.key_bytes()
    db_env, _ = s4p_backup.db_environment(os.environ.get("DATABASE_URL", ""))
    timestamp = now.strftime("%Y%m%d")
    execution = secrets.token_hex(16)
    prefix = f"db-backups/{timestamp}/{execution}"
    with tempfile.TemporaryDirectory(prefix="s4p-db-backup-") as temp:
        folder = pathlib.Path(temp)
        os.chmod(folder, 0o700)
        unencrypted = folder / "pg.dump"
        encrypted = folder / "pg.dump.s4penc"
        subprocess.run(
            ["pg_dump", "--format=custom", "--no-owner", "--no-acl", "--file", str(unencrypted)],
            check=True, env=db_env, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=180,
        )
        s4p_backup.encrypt_file(unencrypted, encrypted, encryption_key)
        unencrypted.unlink()

        parts = []
        with encrypted.open("rb") as input_file:
            number = 0
            while chunk := input_file.read(CHUNK_BYTES):
                number += 1
                if number > 9999:
                    raise RuntimeError("Encrypted backup exceeds supported archive size")
                key = f"{prefix}/part-{number:04d}.bin"
                _json_call(bridge, "upload", key=key, data=chunk,
                           mime="application/octet-stream")
                returned = bridge._request("download", name=key)
                if hashlib.sha256(returned).digest() != hashlib.sha256(chunk).digest():
                    raise RuntimeError("Remote encrypted backup chunk failed integrity verification")
                parts.append({"key": key, "sha256": hashlib.sha256(chunk).hexdigest(),
                              "bytes": len(chunk)})

        with encrypted.open("rb") as archived:
            encrypted_digest = hashlib.file_digest(archived, "sha256").hexdigest()
        manifest = {
            "format": "s4p-aes256-gcm-parts-v1",
            "createdAt": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "parts": parts,
            "encryptedBytes": encrypted.stat().st_size,
            "encryptedSHA256": encrypted_digest,
        }
        manifest_key = f"{prefix}/manifest.json"
        manifest_body = json.dumps(manifest, separators=(",", ":"), sort_keys=True).encode()
        if len(manifest_body) > 64 * 1024:
            raise RuntimeError("Backup manifest is too large")
        _json_call(bridge, "upload", key=manifest_key, data=manifest_body,
                   mime="application/json")
        if bridge._request("download", name=manifest_key) != manifest_body:
            raise RuntimeError("Backup manifest verification failed")

        pointer = {"manifestKey": manifest_key, "createdAt": manifest["createdAt"]}
        _json_call(bridge, "publish",
                   data=json.dumps(pointer, separators=(",", ":")).encode(),
                   mime="application/json")
        latest = _json_call(bridge, "status")
        if latest.get("manifestKey") != manifest_key:
            raise RuntimeError("Backup snapshot was not marked as current")

        logger.info("PASS: encrypted offsite PostgreSQL snapshot committed, chunks=%s bytes=%s",
                    len(parts), manifest["encryptedBytes"])
        return {"skipped": False, "chunks": len(parts), "encryptedBytes": manifest["encryptedBytes"]}


def backup_daemon(stop_event):
    """On Render Free: check on startup, then hourly while process stays alive.

    A 6-hour external availability check wakes the web service on idle.
    This improves continuity but is NOT a substitute for managed backups.
    """
    while not stop_event.is_set():
        try:
            create_encrypted_backup()
        except Exception:
            logger.exception("S4P offsite backup failed; will retry at next check")
        stop_event.wait(3600)
