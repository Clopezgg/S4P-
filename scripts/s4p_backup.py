#!/usr/bin/env python3
"""S4P encrypted Postgres backup to a PRIVATE S3-compatible bucket.

Run INSIDE a trusted backend/cron container with private DB networking.
Never put connection strings or encryption keys in logs or GitHub source.
Requires: PostgreSQL client tools, boto3, cryptography.
"""
import argparse
import base64
import datetime as dt
import os
import pathlib
import re
import secrets
import subprocess
import tempfile
from urllib.parse import unquote, urlsplit

MAGIC = b"S4P-DB-BACKUP-1\n"
BLOCK = 1024 * 1024


def db_environment(url, *, target=False):
    from urllib.parse import parse_qs
    parsed = urlsplit(url.replace("postgresql+psycopg://", "postgresql://", 1))
    if parsed.scheme not in ("postgresql", "postgres"):
        raise RuntimeError("PostgreSQL DSN required")
    if not all((parsed.hostname, parsed.username, parsed.password, parsed.path.strip("/"))):
        raise RuntimeError("Incomplete PostgreSQL connection")
    if target:
        if any(os.environ.get(name) for name in ("PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE")):
            raise RuntimeError("Restore refuses PGHOSTADDR/PGSERVICE/PGSERVICEFILE connection overrides")
        if parsed.hostname not in ("localhost", "127.0.0.1"):
            raise RuntimeError("Restore target must be a local isolated PostgreSQL instance")
        if not re.fullmatch(r"s4p_restore_[a-z0-9_]+", unquote(parsed.path.lstrip("/"))):
            raise RuntimeError("Target database name must match s4p_restore_[a-z0-9_]+")
    opts = parse_qs(parsed.query)
    sslmode = opts.get("sslmode", ["require" if parsed.hostname not in ("localhost", "127.0.0.1") else "disable"])[0]
    if parsed.hostname not in ("localhost", "127.0.0.1") and sslmode != "require":
        raise RuntimeError("Remote backup requires PostgreSQL TLS (sslmode=require)")
    env = os.environ.copy()
    env.update(PGHOST=parsed.hostname, PGPORT=str(parsed.port or 5432),
               PGUSER=unquote(parsed.username), PGPASSWORD=unquote(parsed.password),
               PGDATABASE=unquote(parsed.path.lstrip("/")), PGSSLMODE=sslmode)
    return env, (parsed.hostname, parsed.port or 5432, unquote(parsed.path.lstrip("/")))


def key_bytes():
    raw = os.environ.get("S4P_BACKUP_AES_KEY_B64", "")
    try:
        key = base64.b64decode(raw, validate=True)
    except Exception as exc:
        raise RuntimeError("Missing/invalid S4P_BACKUP_AES_KEY_B64") from exc
    if len(key) != 32:
        raise RuntimeError("S4P_BACKUP_AES_KEY_B64 must encode a 32-byte AES key")
    return key


def encrypt_file(source, output, key):
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    nonce = secrets.token_bytes(12)
    enc = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    with source.open("rb") as src, output.open("wb") as dst:
        dst.write(MAGIC + nonce)
        while block := src.read(BLOCK):
            dst.write(enc.update(block))
        dst.write(enc.finalize())
        dst.write(enc.tag)


def decrypt_file(source, output, key):
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    size = source.stat().st_size
    if size < len(MAGIC) + 12 + 16:
        raise RuntimeError("Invalid encrypted backup size")
    with source.open("rb") as src, output.open("wb") as dst:
        if src.read(len(MAGIC)) != MAGIC:
            raise RuntimeError("Unrecognized S4P backup format")
        nonce = src.read(12)
        src.seek(-16, 2)
        tag = src.read(16)
        src.seek(len(MAGIC) + 12)
        left = size - len(MAGIC) - 12 - 16
        dec = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
        while left:
            block = src.read(min(BLOCK, left))
            if not block:
                raise RuntimeError("Truncated encrypted backup")
            dst.write(dec.update(block))
            left -= len(block)
        dst.write(dec.finalize())  # Authenticates the entire ciphertext


def s3_client():
    import boto3
    endpoint = os.environ.get("S4P_BACKUP_S3_ENDPOINT", "")
    if not endpoint.startswith("https://") or "@" in endpoint:
        raise RuntimeError("Private backup S3 HTTPS endpoint is required")
    access = os.environ.get("S4P_BACKUP_S3_ACCESS_KEY_ID")
    secret = os.environ.get("S4P_BACKUP_S3_SECRET_ACCESS_KEY")
    region = os.environ.get("S4P_BACKUP_S3_REGION")
    bucket = os.environ.get("S4P_BACKUP_S3_BUCKET")
    if not all((access, secret, region, bucket)):
        raise RuntimeError("Backup bucket, region and S3 credentials required")
    client = boto3.client("s3", endpoint_url=endpoint, region_name=region,
                          aws_access_key_id=access, aws_secret_access_key=secret)
    return client, bucket


def perform_backup():
    url = os.environ.get("DATABASE_URL", "")
    env, _identity = db_environment(url)
    key = key_bytes()
    client, bucket = s3_client()
    timestamp = dt.datetime.now(dt.UTC).strftime("%Y/%m/%d/%H%M%S")
    object_key = f"encrypted-postgres/{timestamp}-{secrets.token_hex(6)}.s4penc"
    with tempfile.TemporaryDirectory(prefix="s4p-backup-") as work:
        workdir = pathlib.Path(work)
        os.chmod(workdir, 0o700)
        dump = workdir / "archive.dump"
        encrypted = workdir / "archive.s4penc"
        subprocess.run(["pg_dump", "-Fc", "--no-owner", "--no-acl", "--file", str(dump)],
                       env=env, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        encrypt_file(dump, encrypted, key)
        dump.unlink()
        client.upload_file(str(encrypted), bucket, object_key,
                           ExtraArgs={"ContentType": "application/octet-stream",
                                      "Metadata": {"format": "s4p-aes256-gcm-v1"}})
        client.head_object(Bucket=bucket, Key=object_key)
    print(f"Encrypted off-database backup uploaded and verified: {object_key}")
    return object_key


def validate_empty_restore_target(target_url):
    """Shared fail-closed guard, before any archive download or decryption."""
    target_env, target_id = db_environment(target_url, target=True)
    source_url = os.environ.get("DATABASE_URL")
    if source_url:
        _, source_id = db_environment(source_url)
        if source_id == target_id:
            raise RuntimeError("Refusing to overwrite the source S4P database")
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


def restore_verify_local_only(backup, target_url):
    """Restore locally to a separate, empty, throwaway DB for disaster-recovery tests."""
    target_env, target_id = validate_empty_restore_target(target_url)
    client, bucket = s3_client()
    with tempfile.TemporaryDirectory(prefix="s4p-restore-") as work:
        path = pathlib.Path(work)
        os.chmod(path, 0o700)
        encrypted = path / "archive.s4penc"
        dump = path / "archive.dump"
        client.download_file(bucket, backup, str(encrypted))
        decrypt_file(encrypted, dump, key_bytes())
        subprocess.run(["pg_restore", "--exit-on-error", "--single-transaction", "--no-owner", "--no-acl",
                        "--dbname", target_id[2], str(dump)],
                       env=target_env, check=True, timeout=180, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("PASS: authenticated backup decrypted and restored into isolated test PostgreSQL")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("backup", "restore-verify"))
    parser.add_argument("--object-key")
    parser.add_argument("--target-database-url")
    args = parser.parse_args()
    if args.action == "backup":
        perform_backup()
    else:
        if not args.object_key or not args.target_database_url:
            parser.error("restore-verify requires --object-key and --target-database-url")
        restore_verify_local_only(args.object_key, args.target_database_url)
