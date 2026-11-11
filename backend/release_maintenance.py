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
import re
import secrets
import shutil
import subprocess
import tarfile
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from alembic import command

PARENT = "7b2c1af4849c"
TARGET = "dae6224cb8be"
PREVIOUS_APPLICATION = "8d02c680a1e46cb646b245e3e9ff263675bfc0dc"
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
    width = connection.scalar(text(
        "SELECT character_maximum_length FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name='customer_invoices' AND column_name='status'"
    ))
    if width != 32:
        raise RuntimeError("RevisionAndSchemaDisagree")
    column_type = connection.scalar(text(
        "SELECT data_type FROM information_schema.columns WHERE table_schema='public' "
        "AND table_name='voucher_issuances' AND column_name='contract_context_snapshot'"
    ))
    if column_type not in {None, "jsonb"} or (values[0] == TARGET and column_type != "jsonb"):
        raise RuntimeError("RevisionAndSnapshotSchemaDisagree")
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
    if connection.scalar(text("""
        SELECT count(*) FROM journal_lines l
        JOIN accounting_documents d ON d.id=l.accounting_document_id
        JOIN projects p ON p.id=l.project_id WHERE p.company_id <> d.company_id
    """)):
        raise RuntimeError("CrossCompanyJournalProject")
    if connection.scalar(text("""
        SELECT count(*) FROM voucher_issuances v
        JOIN accounting_documents d ON d.id=v.accounting_document_id
        WHERE v.company_id <> d.company_id
    """)):
        raise RuntimeError("CrossCompanyVoucher")
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
        expression = "to_jsonb(t)"
        if name == "voucher_issuances":
            # Adding an absent nullable column does not change business rows.
            # Non-null historical snapshots remain included in the digest.
            expression = ("CASE WHEN to_jsonb(t)->'contract_context_snapshot' = 'null'::jsonb "
                          "THEN to_jsonb(t) - 'contract_context_snapshot' ELSE to_jsonb(t) END")
        for row in connection.execute(text(
            f"SELECT ({expression})::text FROM public.{quoted} t ORDER BY ({expression})::text"
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
            # Expand-only downgrade retains all historical snapshot values.
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


def verify_previous_application(local_url, engine, folder):
    """Boot the pinned previous S4P source only against the recovered QA DB."""
    with engine.begin() as connection:
        if revision(connection) == TARGET:
            migrate(connection, PARENT)
    archive = Path(folder) / "previous-source.tar.gz"
    url = f"https://api.github.com/repos/Clopezgg/S4P-/tarball/{PREVIOUS_APPLICATION}"
    with urllib.request.urlopen(url, timeout=30) as response, archive.open("wb") as output:
        total = 0
        while block := response.read(1024 * 1024):
            total += len(block)
            if total > 25 * 1024 * 1024:
                raise RuntimeError("PreviousSourceArchiveTooLarge")
            output.write(block)
    unpacked = Path(folder) / "previous-source"
    unpacked.mkdir()
    with tarfile.open(archive) as bundle:
        bundle.extractall(unpacked, filter="data")
    roots = list(unpacked.iterdir())
    if len(roots) != 1 or not (roots[0] / "backend/alembic.ini").is_file():
        raise RuntimeError("UnexpectedPreviousSourceLayout")
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.update(DATABASE_URL=local_url, APP_ENV="testing", GIT_SHA=PREVIOUS_APPLICATION,
               BOOTSTRAP_ADMIN_EMAIL="", BOOTSTRAP_ADMIN_PASSWORD="",
               EDIT_ACCESS_REQUIRED="false", S4P_BACKUP_SCHEDULE_ENABLED="0")
    cwd = roots[0] / "backend"
    run(["python", "-m", "alembic", "current", "--check-heads"], cwd=cwd, env=env)
    process = subprocess.Popen(
        ["python", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8011"],
        cwd=cwd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        until = time.monotonic() + 60
        while True:
            try:
                with urllib.request.urlopen("http://127.0.0.1:8011/api/readyz", timeout=3) as response:
                    if response.status == 200 and json.load(response).get("status") == "ok":
                        break
            except (OSError, urllib.error.URLError):
                if process.poll() is not None or time.monotonic() >= until:
                    raise RuntimeError("PreviousApplicationNotReady") from None
                time.sleep(0.3)
        with urllib.request.urlopen("http://127.0.0.1:8011/api/version", timeout=5) as response:
            if json.load(response).get("gitSha") != PREVIOUS_APPLICATION:
                raise RuntimeError("PreviousApplicationSHAMismatch")
        try:
            urllib.request.urlopen("http://127.0.0.1:8011/api/auth/me", timeout=5)
        except urllib.error.HTTPError as error:
            if error.code != 401:
                raise RuntimeError("PreviousApplicationAuthGuardFailed") from None
        else:
            raise RuntimeError("PreviousApplicationAuthGuardFailed")
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    return True


def authenticated_read_smoke(client, email, password):
    """Real auth/read/logout only. Never creates financial or QA business rows."""
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    if response.status_code != 200:
        raise RuntimeError("ProductionLoginRejected")
    try:
        identity = client.get("/api/auth/me")
        if identity.status_code != 200 or identity.json().get("email", "").casefold() != email.casefold():
            raise RuntimeError("ProductionIdentityMismatch")
        if client.get("/api/master-data/companies").status_code != 200:
            raise RuntimeError("AuthenticatedCompanyReadFailed")
    finally:
        logout = client.post("/api/auth/logout")
        if logout.status_code != 204:
            raise RuntimeError("ProductionLogoutFailed")
    if client.get("/api/auth/me").status_code != 401:
        raise RuntimeError("ProductionSessionNotRevoked")
    return {"productionLoginVerified": True, "authenticatedReadVerified": True,
            "productionLogoutVerified": True, "unauthenticated401Verified": True}


def production_smoke(source):
    import httpx

    email = os.environ.get("BOOTSTRAP_ADMIN_EMAIL", "")
    password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "")
    if not email or not password:
        raise RuntimeError("ProductionSmokeCredentialsRequired")
    origin = "https://s4p-erp-api.onrender.com"
    with source.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        if revision(connection) != TARGET:
            raise RuntimeError("ProductionSchemaNotAtApprovedHead")
        forbidden = connection.scalar(text("""
            SELECT count(*) FROM role_permissions rp JOIN roles r ON r.id=rp.role_id
            JOIN permissions p ON p.id=rp.permission_id
            WHERE r.name='Auditor' AND p.resource='contract.payment_schedule' AND p.action='manage'
        """))
        if forbidden:
            raise RuntimeError("AuditorWriteGrantStillPresent")
    with httpx.Client(base_url=origin, headers={"Origin": origin}, timeout=30, follow_redirects=False) as client:
        version = client.get("/api/version")
        if version.status_code != 200 or version.json().get("gitSha") != os.environ["S4P_APPROVED_MAIN_SHA"]:
            raise RuntimeError("ProductionSHAMismatch")
        for path in ("/api/readyz", "/api/backupz"):
            response = client.get(path)
            if response.status_code != 200 or response.json().get("status") != "ok":
                raise RuntimeError("ProductionHealthCheckFailed")
        login = client.get("/login")
        if login.status_code != 200:
            raise RuntimeError("ProductionLoginHTMLFailed")
        assets = re.findall(r'(?:src|href)="(/assets/[^"?]+\.(?:js|css))"', login.text)
        if not any(p.endswith(".css") for p in assets) or not any(p.endswith(".js") for p in assets):
            raise RuntimeError("ProductionAssetsMissing")
        for path in assets:
            if client.get(path).status_code != 200:
                raise RuntimeError("ProductionAssetDownloadFailed")
        result = authenticated_read_smoke(client, email, password)
    publish(status="success", stage="complete", operation="smoke", deployedSHA=os.environ["S4P_APPROVED_MAIN_SHA"],
            productionAssetsVerified=True, auditorWriteGrantRevoked=True, **result)


def recover():
    operation = os.environ.get("S4P_RELEASE_OPERATION", "preflight")
    if operation not in {"preflight", "migrate", "rollback", "smoke"}:
        raise RuntimeError("UnsupportedOperation")
    if operation != "preflight":
        approved_sha = os.environ.get("S4P_APPROVED_MAIN_SHA", "")
        if (len(approved_sha) != 40 or approved_sha != os.environ.get("RENDER_GIT_COMMIT")
                or os.environ.get("S4P_APPROVE_SCHEMA_CHANGE") != TARGET):
            raise RuntimeError("ExplicitRevisionAndSHAAcceptanceRequired")
    # Read settings only after validating operation; never run app bootstrap.
    from app.core.config import get_settings
    from app.services.backup_worker import _bridge, _json_call, create_encrypted_backup
    from restore_from_supabase import restore_to_test_database

    source_url = get_settings().database_url
    source_address = make_url(source_url)
    if (not (source_address.host or "").startswith("dpg-dbh8j41srm7s73f3u1b0-a")
            or source_address.database != "s4p_postgres_staging"):
        raise RuntimeError("UnexpectedProductionDatabase")
    source = create_engine(source_url, pool_pre_ping=True, connect_args={"sslmode": "require"})
    try:
        if operation == "smoke":
            production_smoke(source)
            return
        with source.connect() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            source_revision = revision(connection)
            integrity(connection)
        # The last scheduled backup may predate a separately approved schema
        # change. Take a fresh encrypted snapshot before this recovery drill;
        # pg_dump only reads production, immutable archives remain offsite.
        publish(stage="taking_current_schema_backup")
        create_encrypted_backup(force=True)
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
                 "--auth-host=scram-sha-256", "--auth-local=trust", "--no-locale", "--encoding=UTF8"])
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
                publish(stage="checking_restored_integrity")
                with local.connect() as connection:
                    connection.execute(text("SET TRANSACTION READ ONLY"))
                    restored_revision = revision(connection)
                    checks = integrity(connection)
                if restored_revision != source_revision and not (
                    restored_revision == PARENT and source_revision == TARGET
                ):
                    raise RuntimeError("BackupRevisionMismatch")
                publish(stage="rehearsing_schema")
                schema_roundtrip(local)
                publish(stage="rehearsing_previous_application")
                verify_previous_application(local_url, local, folder)
                publish(stage="verified", restoreVerified=True, rollbackRehearsed=True,
                        rollbackApplicationReady=True, rollbackApplicationSHA=PREVIOUS_APPLICATION,
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
