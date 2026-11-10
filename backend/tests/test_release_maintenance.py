"""Real PG DDL transactions: recovery must never stamp or lose business rows."""
import uuid
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

import release_maintenance as maintenance
from alembic import command
from app.core.config import get_settings
from app.services.bootstrap_service import bootstrap_admin_if_needed


@pytest.fixture
def recovery_database():
    base = make_url(get_settings().database_url)
    if base.host not in {"127.0.0.1", "localhost"}:
        raise RuntimeError("Recovery tests require local PostgreSQL")
    name = "nexora_recovery_" + uuid.uuid4().hex
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_engine(base.set(database=name))
    try:
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, maintenance.PARENT)
        with Session(engine) as session:
            bootstrap_admin_if_needed(session)
        yield engine
    finally:
        engine.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{name}"'))
        admin.dispose()


def snapshot(engine):
    with engine.connect() as connection:
        return (maintenance.revision(connection), maintenance.fingerprint(connection),
                connection.scalar(text("SELECT character_maximum_length FROM information_schema.columns "
                                       "WHERE table_name='customer_invoices' AND column_name='status'")))


def test_real_rehearsal_and_controlled_migration_preserve_all_rows(recovery_database):
    engine = recovery_database
    before = snapshot(engine)
    assert maintenance.schema_roundtrip(engine)
    assert snapshot(engine) == before
    assert maintenance.change_source(engine, "migrate", rehearsal_passed=True) == maintenance.TARGET
    widened = snapshot(engine)
    assert widened == (maintenance.TARGET, before[1], 32)
    assert maintenance.change_source(engine, "rollback", rehearsal_passed=True) == maintenance.PARENT
    assert snapshot(engine) == before


def test_verification_failure_rolls_back_actual_ddl_and_revision(recovery_database, monkeypatch):
    engine = recovery_database
    before = snapshot(engine)
    actual = maintenance.fingerprint
    calls = 0

    def failed_verification(connection):
        nonlocal calls
        calls += 1
        result = actual(connection)
        return b"injected verification failure" if calls == 2 else result

    with monkeypatch.context() as scoped:
        scoped.setattr(maintenance, "fingerprint", failed_verification)
        with pytest.raises(RuntimeError, match="SourceRowsChanged"):
            maintenance.change_source(engine, "migrate", rehearsal_passed=True)
    # New connection: real ALTER and Alembic revision update both rolled back.
    assert snapshot(engine) == before


def test_missing_rehearsal_and_changed_revision_refuse_source_mutation(recovery_database):
    engine = recovery_database
    before = snapshot(engine)
    with pytest.raises(RuntimeError, match="SourceMutationNotAuthorized"):
        maintenance.change_source(engine, "migrate", rehearsal_passed=False)
    with pytest.raises(RuntimeError, match="SourceRevisionChanged"):
        maintenance.change_source(engine, "rollback", rehearsal_passed=True)
    assert snapshot(engine) == before


def test_worker_failure_never_publishes_exception_credentials(monkeypatch, capsys):
    def fail():
        raise RuntimeError("sensitive-dsn-and-credential")

    monkeypatch.setattr(maintenance, "recover", fail)
    monkeypatch.setattr(maintenance, "REPORT", {"status": "running"})
    maintenance.worker()
    output = capsys.readouterr().out
    assert "sensitive-dsn-and-credential" not in output
    assert '"errorType": "RuntimeError"' in output
    assert '"status": "failed"' in output
