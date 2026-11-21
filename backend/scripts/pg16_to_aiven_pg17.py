#!/usr/bin/env python3
"""Read-only Render PG16 -> *empty* Aiven PG17 clone with full-row parity.

Never changes Render source, application's DATABASE_URL or deploys production.
Refuses an occupied target, an unexpected host, unverified TLS, or missing
backups/maintenance gates. Run ONLY from the private Render network.
Secrets come from environment, never command arguments.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlsplit

SOURCE_HOST_PREFIX = "dpg-dbh8j41srm7s73f3u1b0-a"
SOURCE_DB = "s4p_postgres_staging"
TABLE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


@dataclass(frozen=True)
class Connection:
    host: str
    port: int
    username: str
    password: str
    database: str
    sslmode: str


def parse_connection(uri: str) -> Connection:
    parsed = urlsplit(uri.replace("postgresql+psycopg://", "postgresql://", 1))
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise RuntimeError("PostgreSQL connection string required")
    if not all((parsed.hostname, parsed.username, parsed.password, parsed.path.lstrip("/"))):
        raise RuntimeError("Incomplete PostgreSQL connection")
    query = parse_qs(parsed.query)
    if parsed.fragment or set(query) - {"sslmode"}:
        raise RuntimeError("Unsupported PostgreSQL URI options")
    return Connection(
        host=parsed.hostname, port=parsed.port or 5432,
        username=unquote(parsed.username), password=unquote(parsed.password),
        database=unquote(parsed.path.lstrip("/")),
        sslmode=query.get("sslmode", ["prefer"])[0],
    )


def validate_endpoints(source: Connection, target: Connection, expected_target_host: str) -> None:
    if not source.host.startswith(SOURCE_HOST_PREFIX) or source.database != SOURCE_DB:
        raise RuntimeError("Unrecognized Render PostgreSQL source")
    if (not expected_target_host or target.host != expected_target_host
            or not target.host.endswith(".aivencloud.com")
            or target.database != "defaultdb"):
        raise RuntimeError("Unapproved or unexpected Aiven PostgreSQL target")
    if (source.host, source.port, source.database) == (target.host, target.port, target.database):
        raise RuntimeError("Source and target must differ")
    if target.sslmode != "verify-full":
        raise RuntimeError("Aiven TLS verify-full is mandatory")


def pg_environment(connection: Connection, *, ca_file: str | None = None,
                   source: bool = False) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
    env.update(
        PGHOST=connection.host, PGPORT=str(connection.port),
        PGUSER=connection.username, PGPASSWORD=connection.password,
        PGDATABASE=connection.database, PGSSLMODE=connection.sslmode,
        PGCONNECT_TIMEOUT="12", PGAPPNAME="s4p_cutover_clone",
    )
    if source:
        env["PGOPTIONS"] = "-c default_transaction_read_only=on"
    else:
        if not ca_file or not pathlib.Path(ca_file).is_file():
            raise RuntimeError("Aiven project CA certificate is required")
        env["PGSSLROOTCERT"] = ca_file
    return env


def run_sql(env: dict[str, str], sql: str) -> list[str]:
    output = subprocess.run(
        ["psql", "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-c", sql],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        check=True, timeout=120, text=True,
    ).stdout
    return [line for line in output.splitlines() if line]


def one(env: dict[str, str], sql: str) -> str:
    values = run_sql(env, sql)
    if len(values) != 1:
        raise RuntimeError("Unexpected result row count")
    return values[0]


def tables(env: dict[str, str]) -> list[str]:
    names = run_sql(env, "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
    if any(not TABLE.fullmatch(name) for name in names):
        raise RuntimeError("Unrecognized table identifier")
    return names


def nonempty_objects(env: dict[str, str]) -> int:
    return int(one(env, """
        SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relkind IN ('r','p','S','v','m','f')
    """))


def financial_integrity(env: dict[str, str]) -> None:
    if one(env, "SELECT count(*) FROM pg_constraint WHERE contype='f' AND NOT convalidated") != "0":
        raise RuntimeError("Unvalidated foreign keys")
    if one(env, """
        SELECT count(*) FROM (
          SELECT d.id FROM accounting_documents d
          LEFT JOIN journal_lines l ON l.accounting_document_id=d.id
          WHERE d.status IN ('POSTED','REVERSED')
          GROUP BY d.id
          HAVING coalesce(sum(l.debit_amount),0)<>coalesce(sum(l.credit_amount),0)
             OR coalesce(sum(l.debit_amount),0)<=0
        ) bad
    """) != "0":
        raise RuntimeError("Unbalanced posted financial ledger")
    for name in ("users", "roles"):
        if one(env, f"SELECT count(*) FROM {name}") == "0":
            raise RuntimeError("Required identity records missing")


def fingerprint_table(env: dict[str, str], name: str) -> tuple[int, str]:
    quoted = '"' + name.replace('"', '""') + '"'
    query = f"COPY (SELECT to_jsonb(t)::text FROM public.{quoted} t ORDER BY to_jsonb(t)::text) TO STDOUT"
    process = subprocess.Popen(
        ["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-c", query],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    digest = hashlib.sha256()
    rows = 0
    assert process.stdout is not None
    with process.stdout:
        while chunk := process.stdout.read(65536):
            digest.update(chunk)
            rows += chunk.count(b"\n")
    if process.wait(timeout=120) != 0:
        raise RuntimeError("Unable to fingerprint all records")
    return rows, digest.hexdigest()


def fingerprint_all(env: dict[str, str]) -> tuple[list[str], dict[str, tuple[int, str]]]:
    names = tables(env)
    return names, {name: fingerprint_table(env, name) for name in names}


def clone() -> None:
    source = parse_connection(os.environ.get("DATABASE_URL", ""))
    target = parse_connection(os.environ.get("S4P_AIVEN_TARGET_DATABASE_URL", ""))
    validate_endpoints(source, target, os.environ.get("S4P_AIVEN_EXPECTED_HOST", ""))
    source_env = pg_environment(source, source=True)
    target_env = pg_environment(target, ca_file=os.environ.get("S4P_AIVEN_CA_FILE"))
    if not all(shutil.which(program) for program in ("pg_dump", "pg_restore", "psql")):
        raise RuntimeError("PostgreSQL 17 client tools unavailable")
    if int(one(source_env, "SELECT current_setting('server_version_num')")) // 10000 != 16:
        raise RuntimeError("Expected source PostgreSQL 16")
    if int(one(target_env, "SELECT current_setting('server_version_num')")) // 10000 != 17:
        raise RuntimeError("Expected destination PostgreSQL 17")
    if nonempty_objects(target_env):
        raise RuntimeError("Target is not empty; refusing restore")
    initial_tables = tables(source_env)
    needed = {"alembic_version", "users", "roles", "companies",
              "accounting_documents", "journal_lines"}
    if not needed <= set(initial_tables):
        raise RuntimeError("Source ERP tables are incomplete")
    financial_integrity(source_env)
    for flag in ("S4P_MIGRATION_BACKUP_VERIFIED",
                 "S4P_AIVEN_IP_ALLOWLIST_RESTRICTED",
                 "S4P_MIGRATION_WRITE_FREEZE_CONFIRMED"):
        if os.environ.get(flag) != "1":
            raise RuntimeError("Operational backup, network or write-freeze gate missing")
    print(json.dumps({
        "phase": "preflight", "sourcePG": 16, "targetPG": 17,
        "sourcePublicTables": len(initial_tables), "targetEmpty": True,
        "writesToSource": False, "productionCutover": False,
    }), flush=True)
    before = fingerprint_all(source_env)
    if nonempty_objects(target_env):
        raise RuntimeError("Destination changed during preflight")
    with tempfile.TemporaryDirectory(prefix="s4p-aiven-clone-") as folder:
        os.chmod(folder, 0o700)
        archive = pathlib.Path(folder) / "snapshot.pgcustom"
        subprocess.run(
            ["pg_dump", "-Fc", "--no-owner", "--no-acl", "--file", str(archive)],
            env=source_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            check=True, timeout=300,
        )
        if fingerprint_all(source_env) != before:
            raise RuntimeError("Source drifted during snapshot; destination unchanged")
        subprocess.run(
            ["pg_restore", "--exit-on-error", "--single-transaction", "--no-owner",
             "--no-acl", "--dbname", target.database, str(archive)],
            env=target_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            check=True, timeout=300,
        )
    src_final = fingerprint_all(source_env)
    dst_final = fingerprint_all(target_env)
    if src_final != before or src_final != dst_final:
        raise RuntimeError("Source/target row-content mismatch; NO CUTOVER")
    financial_integrity(target_env)
    if one(source_env, "SELECT version_num FROM alembic_version") != one(
        target_env, "SELECT version_num FROM alembic_version"
    ):
        raise RuntimeError("Alembic schema version mismatch")
    print(json.dumps({
        "phase": "clone_verified", "tables": len(src_final[0]),
        "allRowsEqual": True, "foreignKeysValidated": True,
        "ledgerBalanced": True, "alembicEqual": True,
        "writesToSource": False, "productionCutover": False,
    }), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Private PG16 to empty Aiven PG17 clone; never changes production connection"
    )
    parser.add_argument("--clone-to-empty-target", action="store_true")
    args = parser.parse_args()
    if not args.clone_to_empty_target:
        parser.error("No default operation. Pass --clone-to-empty-target after the documented gates")
    clone()
