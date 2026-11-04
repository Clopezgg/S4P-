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


def _validate_empty_isolated_target(target_dsn: str):
    """Fail closed before downloading or decrypting any production backup."""
    target_env, target_id = s4p_backup.db_environment(target_dsn)
    if target_id[0] not in ("localhost", "127.0.0.1"):
        raise RuntimeError("Restore target must be a local isolated PostgreSQL instance")
    if not target_id[2].startswith("s4p_restore_"):
        raise RuntimeError("Target database name must start with s4p_restore_")

    source_url = os.environ.get("DATABASE_URL")
    if source_url:
        _, source_id = s4p_backup.db_environment(source_url)
        if source_id == target_id:
            raise RuntimeError("Refusing to overwrite the source S4P database")

    # Inspect metadata only. All target objects must be absent before restore.
    # This prevents a partial import or overwrite of an existing local ERP.
    sql = (
        "SELECT count(*) FROM pg_class c "
        "JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname <> 'information_schema' "
        "AND n.nspname NOT LIKE 'pg_%' "
        "AND c.relkind IN ('r','p','v','m','S','f')"
    )
    result = subprocess.run(
        ["psql", "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-c", sql],
        env=target_env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, check=True, timeout=30,
    )
    if result.stdout.strip() != "0":
        raise RuntimeError("Restore target is not empty; refusing to modify it")
    return target_env, target_id


def restore_to_test_database(target_dsn: str) -> None:
    target_env, target_id = _validate_empty_isolated_target(target_dsn)
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

    # Disaster recovery also works after Render's source DATABASE_URL expires.
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
            ["pg_restore", "--exit-on-error", "--single-transaction", "--no-owner", "--no-acl",
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
