#!/usr/bin/env python3
"""Restore the latest encrypted S4P backup to an isolated LOCAL PostgreSQL DB.

Never restores into the live Render database. Requires the exact AES-256 key,
signed Supabase bridge credentials and an EMPTY local throwaway database.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import tempfile

import s4p_backup
from app.services.backup_worker import _bridge, _json_call


def restore_to_test_database(target_dsn: str) -> None:
    bridge = _bridge()
    latest = _json_call(bridge, "status")
    if not latest.get("available"):
        raise RuntimeError("No completed offsite backup was found")
    manifest_key = latest.get("manifestKey", "")
    if not isinstance(manifest_key, str) or not manifest_key.endswith("/manifest.json"):
        raise RuntimeError("Malformed offsite backup index")
    manifest = json.loads(bridge._request("download", name=manifest_key))
    if manifest.get("format") != "s4p-aes256-gcm-parts-v1":
        raise RuntimeError("Unknown backup archive format")
    parts = manifest.get("parts")
    if not isinstance(parts, list) or not parts or len(parts) > 9999:
        raise RuntimeError("Invalid backup chunk manifest")

    target_env, target_id = s4p_backup.db_environment(target_dsn)
    if target_id[0] not in ("localhost", "127.0.0.1"):
        raise RuntimeError("Restore target must be a local isolated PostgreSQL instance")
    # Disaster recovery must work even when the primary Render database has
    # expired and its DATABASE_URL is no longer available.
    source_url = os.environ.get("DATABASE_URL")
    if source_url:
        _, source_id = s4p_backup.db_environment(source_url)
        if source_id == target_id:
            raise RuntimeError("Refusing to overwrite the source S4P database")
    key = s4p_backup.key_bytes()

    with tempfile.TemporaryDirectory(prefix="s4p-backup-restore-") as tmp:
        folder = pathlib.Path(tmp)
        os.chmod(folder, 0o700)
        encrypted = folder / "backup.s4penc"
        decrypted = folder / "backup.pgcustom"
        digest = hashlib.sha256()
        total = 0
        with encrypted.open("wb") as out:
            for number, part in enumerate(parts, 1):
                item = part.get("key")
                if not isinstance(item, str) or item != manifest_key.removesuffix("manifest.json") + f"part-{number:04d}.bin":
                    raise RuntimeError("Invalid backup chunk path")
                body = bridge._request("download", name=item)
                if hashlib.sha256(body).hexdigest() != part.get("sha256") or len(body) != part.get("bytes"):
                    raise RuntimeError("Encrypted backup chunk integrity failure")
                total += len(body)
                digest.update(body)
                out.write(body)
        if total != manifest.get("encryptedBytes") or digest.hexdigest() != manifest.get("encryptedSHA256"):
            raise RuntimeError("Whole-backup integrity failure")
        s4p_backup.decrypt_file(encrypted, decrypted, key)
        subprocess.run(
            ["pg_restore", "--exit-on-error", "--no-owner", "--no-acl",
             "--dbname", target_id[2], str(decrypted)],
            check=True, env=target_env, timeout=180,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    print("PASS: latest encrypted offsite snapshot restored into isolated local PostgreSQL")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-database-url", required=True)
    args = parser.parse_args()
    restore_to_test_database(args.target_database_url)
