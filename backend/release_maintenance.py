"""Controlled recovery inside Render's private network, never an ERP endpoint.

Default preflight only SELECTs production. Restore/rehearsal writes are confined
to a disposable loopback PG cluster. Explicit env-selected migrate/rollback
operations are restricted to the one reviewed revision, after real restoration.
HTTP exposes only a fixed sanitized report; it accepts no operations or SQL.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from alembic import command

PARENT = "eb8ce8e18b2d"
TARGET = "7b2c1af4849c"
REPORT = {"status": "running", "stage": "initializing"}
REPORT_LOCK = threading.Lock()


def publish(**values):
    with REPORT_LOCK:
        REPORT.update(values)
        payload = json.dumps(REPORT, sort_keys=True)
    print("S4P_RECOVERY " + payload, flush=True)


def run(argv, **kwargs):
    # Never forward tool stderr, connection strings, rows or credentials.
    return subprocess.run(argv, check=True, timeout=180,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)


def revision(connection):
    values = connection.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
    if len(values) != 1 or values[0] not in {PARENT, TARGET}:
        raise RuntimeError("UnexpectedRevision")
    return values[0]


def integrity(connection):
    tables = set(connection.execute(text(
        "SELECT tablename FROM pg_tables WHERE schemaname='public'"
    )).scalars())
    required = {"companies", "users", "roles", "role_permissions", "journal_lines",
                "accounting_documents", "voucher_issuances", "voucher_verifications"}
    if not required <= tables:
        raise RuntimeError("MissingERPTables")
    if connection.scalar(text("SELECT count(*) FROM pg_constraint WHERE contype='f' AND NOT convalidated")):
        raise RuntimeError("UnvalidatedForeignKeys")
    if connection.scalar(text("""
        SELECT count(*) FROM (
          SELECT d.id FROM accounting_documents d LEFT JOIN journal_lines l
            ON l.accounting_document_id=d.id
          WHERE d.status IN ('POSTED','REVERSED') GROUP BY d.id
          HAVING coalesce(sum(l.debit_amount),0) <> coalesce(sum(l.credit_amount),0)
            OR coalesce(sum(l.debit_amount),0) <= 0
        ) broken
    """)):
        raise RuntimeError("UnbalancedLedger")
    for name in ("users", "roles", "role_permissions"):
        if connection.scalar(text(f'SELECT count(*) FROM "{name}"')) == 0:
            raise RuntimeError("MissingIdentityData")
    return {
        "foreignKeysValidated": True, "ledgerBalanced": True,
        "identityRowsPresent": True, "erpTablesPresent": True,
        "companiesPresent": bool(connection.scalar(text("SELECT count(*) FROM companies"))),
        "receiptsPresent": bool(connection.scalar(text("SELECT count(*) FROM voucher_issuances"))),
        "postedDocumentsPresent": bool(connection.scalar(text(
            "SELECT count(*) FROM accounting_documents WHERE status IN ('POSTED','REVERSED')"
        ))),
    }


def fingerprint(connection):
    """Full row-content digest kept in memory only, never published."""
    digest = hashlib.sha256()
    names = connection.execute(text(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename <> 'alembic_version' ORDER BY tablename"
    )).scalars().all()
    for name in names:
        quoted = connection.dialect.identifier_preparer.quote_identifier(name)
        digest.update(name.encode() + b"\0")
        for row in connection.execute(text(
            f"SELECT to_jsonb(t)::text FROM public.{quoted} t ORDER BY to_jsonb(t)::text"
        )).scalars():
            data = row.encode()
            digest.update(len(data).to_bytes(8, "big") + data)
    return digest.digest()


def migrate(connection, destination):
    cfg = Config(str(Path(__file__).parent / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).parent / "alembic"))
    cfg.attributes["connection"] = connection
    if destination == TARGET:
        command.upgrade(cfg, TARGET)
    elif destination == PARENT:
        command.downgrade(cfg, PARENT)
    else:
        raise RuntimeError("UnexpectedMigrationTarget")


def schema_roundtrip(engine):
    with engine.begin() as connection:
        original = revision(connection)
        before = fingerprint(connection)
        if original == TARGET:
            # Narrowing may correctly reject real long statuses. Never truncate.
            migrate(connection, PARENT)
        migrate(connection, TARGET)
        if fingerprint(connection) != before:
            raise RuntimeError("UpgradeChangedRows")
        migrate(connection, PARENT)
        if fingerprint(connection) != before or revision(connection) != PARENT:
            raise RuntimeError("DowngradeChangedRows")
        if original == TARGET:
            migrate(connection, TARGET)
        integrity(connection)
    return True


def change_source(engine, operation, rehearsal_passed):
    if operation not in {"migrate", "rollback"} or not rehearsal_passed:
        raise RuntimeError("SourceMutationNotAuthorized")
    expected, destination = (PARENT, TARGET) if operation == "migrate" else (TARGET, PARENT)
    with engine.connect().execution_options(isolation_level="SERIALIZABLE") as connection:
        with connection.begin():
            connection.execute(text("SET LOCAL lock_timeout='5s'"))
            connection.execute(text("SET LOCAL statement_timeout='30s'"))
            connection.execute(text("SELECT pg_advisory_xact_lock(73470013)"))
            if revision(connection) != expected:
                raise RuntimeError("SourceRevisionChanged")
            integrity(connection)
            before = fingerprint(connection)
            migrate(connection, destination)
            if fingerprint(connection) != before:
                raise RuntimeError("SourceRowsChanged")
            if revision(connection) != destination:
                raise RuntimeError("SourceRevisionMismatch")
            integrity(connection)
    return destination


def recover():
    operation = os.environ.get("S4P_RELEASE_OPERATION", "preflight")
    if operation not in {"preflight", "migrate", "rollback"}:
        raise RuntimeError("UnsupportedOperation")
    if operation != "preflight":
        approved_sha = os.environ.get("S4P_APPROVED_MAIN_SHA", "")
        if (len(approved_sha) != 40 or approved_sha != os.environ.get("RENDER_GIT_COMMIT")
                or os.environ.get("S4P_APPROVE_SCHEMA_CHANGE") != TARGET):
            raise RuntimeError("ExplicitRevisionAndSHAAcceptanceRequired")
    # Read settings only after validating operation; never run app bootstrap.
    from app.core.config import get_settings
    from app.services.backup_worker import _bridge, _json_call
    from restore_from_supabase import restore_to_test_database

    source_url = get_settings().database_url
    source_address = make_url(source_url)
    if (not (source_address.host or "").startswith("dpg-dbh8j41srm7s73f3u1b0-a")
            or source_address.database != "s4p_postgres_staging"):
        raise RuntimeError("UnexpectedProductionDatabase")
    source = create_engine(source_url, pool_pre_ping=True, connect_args={"sslmode": "require"})
    try:
        with source.connect() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            source_revision = revision(connection)
            integrity(connection)
        latest = _json_call(_bridge(), "status")
        created = datetime.fromisoformat(latest["createdAt"].replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - created).total_seconds()
        if not latest.get("available") or not 0 <= age <= 36 * 3600:
            raise RuntimeError("BackupNotFresh")
        publish(stage="restoring", operation=operation, sourceRevision=source_revision,
                backupCreatedAt=created.isoformat(), backupAgeSeconds=round(age))
        with tempfile.TemporaryDirectory(prefix="s4p-independent-recovery-") as folder:
            cluster = Path(folder) / "pgdata"
            password = secrets.token_urlsafe(32)
            password_file = Path(folder) / "password"
            password_file.write_text(password)
            password_file.chmod(0o600)
            run(["initdb", "-D", str(cluster), "-U", "recovery", "--pwfile", str(password_file),
                 "--auth-host=scram-sha-256", "--auth-local=trust", "--no-locale"])
            options = (f"-h 127.0.0.1 -k {folder} -p 55432 -c shared_buffers=16MB "
                       "-c max_connections=10 -c work_mem=1MB")
            run(["pg_ctl", "-D", str(cluster), "-o", options, "-w", "start", "-l", str(Path(folder) / "postgres.log")])
            local_url = f"postgresql+psycopg://recovery:{password}@127.0.0.1:55432/s4p_restore_release"
            env = os.environ.copy()
            env.update(PGHOST="127.0.0.1", PGPORT="55432", PGUSER="recovery",
                       PGPASSWORD=password, PGSSLMODE="disable")
            started = time.monotonic()
            local = None
            try:
                run(["createdb", "s4p_restore_release"], env=env)
                restore_to_test_database(local_url)
                local = create_engine(local_url)
                with local.connect() as connection:
                    connection.execute(text("SET TRANSACTION READ ONLY"))
                    restored_revision = revision(connection)
                    checks = integrity(connection)
                if restored_revision != source_revision and not (
                    restored_revision == PARENT and source_revision == TARGET
                ):
                    raise RuntimeError("BackupRevisionMismatch")
                schema_roundtrip(local)
                publish(stage="verified", restoreVerified=True, rollbackRehearsed=True,
                        rollbackPreservesAllRows=True, restoreSeconds=round(time.monotonic() - started, 3),
                        restoredRevision=restored_revision, **checks)
                if operation != "preflight":
                    destination = change_source(source, operation, rehearsal_passed=True)
                    publish(stage="schema_changed", sourceRevision=destination, sourceRowsPreserved=True)
            finally:
                if local is not None:
                    local.dispose()
                run(["pg_ctl", "-D", str(cluster), "-m", "fast", "-w", "stop"])
        publish(status="success", stage="complete", temporaryClusterRemoved=True)
    finally:
        source.dispose()


class StatusHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in {"/healthz", "/status"}:
            self.send_error(404)
            return
        with REPORT_LOCK:
            body = json.dumps({"status": "ok"} if self.path == "/healthz" else REPORT).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def worker():
    try:
        recover()
    except Exception as exc:
        # No exception messages: drivers/HTTP clients can embed credentials.
        publish(status="failed", errorType=type(exc).__name__)


if __name__ == "__main__":
    if not shutil.which("postgres"):
        raise RuntimeError("PostgresServerRequired")
    publish(gitSha=os.environ.get("RENDER_GIT_COMMIT", "unknown"))
    threading.Thread(target=worker, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8000"))), StatusHandler).serve_forever()
