"""Fail-closed checks for restoring a REAL backup into a local disposable DB only."""
from __future__ import annotations

import subprocess
import sys
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import pytest

# The Render image installs s4p_backup.py at /app; local checkouts use scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

_validate_empty_isolated_target = import_module('restore_from_supabase')._validate_empty_isolated_target


def _dsn(db: str, host: str = "localhost") -> str:
    return f"postgresql+psycopg://qa:dummy@{host}:5432/{db}"


def test_empty_isolated_target_can_be_inspected_without_writing(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(stdout="0\n")

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(subprocess, "run", fake_run)
    _env, identity = _validate_empty_isolated_target(_dsn("s4p_restore_verification"))
    assert identity == ("localhost", 5432, "s4p_restore_verification")
    assert len(calls) == 1
    command, options = calls[0]
    assert command[0] == "psql"
    assert "-c" in command
    assert "SELECT count(*) FROM pg_class" in command[-1]
    assert options["check"] is True
    assert options["stderr"] == subprocess.DEVNULL


@pytest.mark.parametrize("table_count", ["1\n", "14\n", "not-a-number\n"])
def test_restore_refuses_existing_objects_or_unknown_output(monkeypatch, table_count):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(
        subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout=table_count),
    )
    with pytest.raises(RuntimeError, match="not empty"):
        _validate_empty_isolated_target(_dsn("s4p_restore_verification"))


def test_restore_refuses_remote_target_before_db_access(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: pytest.fail("must not query"))
    with pytest.raises(RuntimeError, match="local isolated"):
        _validate_empty_isolated_target(_dsn("s4p_restore_verification", "db.example.test"))


def test_restore_refuses_unmarked_local_database(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: pytest.fail("must not query"))
    with pytest.raises(RuntimeError, match="s4p_restore_"):
        _validate_empty_isolated_target(_dsn("production"))


def test_restore_refuses_own_source_database(monkeypatch):
    url = _dsn("s4p_restore_verification")
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: pytest.fail("must not query"))
    with pytest.raises(RuntimeError, match="source S4P database"):
        _validate_empty_isolated_target(url)


@pytest.mark.parametrize("variable", ["PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE"])
@pytest.mark.parametrize("entry", ["bridge", "legacy-s3"])
def test_all_python_restore_paths_reject_connection_overrides(monkeypatch, variable, entry):
    backup = import_module('s4p_backup')
    monkeypatch.setenv(variable, '192.0.2.1' if variable == 'PGHOSTADDR' else 'unexpected')
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('must reject before DB access'))
    target = _dsn('s4p_restore_verification')
    with pytest.raises(RuntimeError, match='connection overrides'):
        if entry == 'bridge':
            _validate_empty_isolated_target(target)
        else:
            backup.restore_verify_local_only('unused-object', target)


@pytest.mark.parametrize("dbname", ["production", "s4p_restore_qa host=db.example.test", "s4p_restore_qa?hostaddr=192.0.2.1"])
def test_legacy_restore_rejects_unmarked_or_conninfo_database_names(monkeypatch, dbname):
    from urllib.parse import quote

    backup = import_module('s4p_backup')
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('must reject before DB access'))
    with pytest.raises(RuntimeError, match='s4p_restore_'):
        backup.restore_verify_local_only('unused-object', _dsn(quote(dbname, safe='')))


def test_python_restore_guard_preserves_real_existing_local_data(monkeypatch):
    import os
    import uuid

    import psycopg

    backup = import_module('s4p_backup')
    name = 's4p_restore_guard_' + uuid.uuid4().hex
    password = os.environ.get('POSTGRES_PASSWORD', 'nexora')
    env = {k: v for k, v in os.environ.items() if k not in {'PGHOSTADDR', 'PGSERVICE', 'PGSERVICEFILE'}}
    env.update(PGHOST='127.0.0.1', PGPORT='5432', PGUSER='nexora', PGPASSWORD=password)
    subprocess.run(['createdb', name], env=env, check=True, timeout=30)
    target = f'postgresql+psycopg://nexora:{password}@127.0.0.1:5432/{name}'
    try:
        assert _validate_empty_isolated_target(target)[1][2] == name
        with psycopg.connect(host='127.0.0.1', port=5432, user='nexora', password=password, dbname=name) as conn:
            conn.execute('CREATE TABLE restore_guard_probe (value integer PRIMARY KEY)')
            conn.execute('INSERT INTO restore_guard_probe VALUES (17)')
        monkeypatch.setattr(backup, 's3_client', lambda: pytest.fail('must reject before storage access'))
        for restore in [lambda: _validate_empty_isolated_target(target),
                        lambda: backup.restore_verify_local_only('unused-object', target)]:
            with pytest.raises(RuntimeError, match='not empty'):
                restore()
        with psycopg.connect(host='127.0.0.1', port=5432, user='nexora', password=password, dbname=name) as conn:
            assert conn.execute('SELECT value FROM restore_guard_probe').fetchone() == (17,)
    finally:
        subprocess.run(['dropdb', name], env=env, check=True, timeout=30)


def test_legacy_restore_rolls_back_real_postgres_on_late_archive_failure(monkeypatch, tmp_path):
    """Fault injection for transport only; crypto, CLI and PostgreSQL are real."""
    import base64
    import os
    import uuid

    import psycopg

    backup = import_module('s4p_backup')
    suffix = uuid.uuid4().hex
    source = 's4p_restore_seed_' + suffix
    target = 's4p_restore_atomic_' + suffix
    password = os.environ.get('POSTGRES_PASSWORD', 'nexora')
    env = {k: v for k, v in os.environ.items() if k not in {'PGHOSTADDR', 'PGSERVICE', 'PGSERVICEFILE'}}
    env.update(PGHOST='127.0.0.1', PGPORT='5432', PGUSER='nexora', PGPASSWORD=password)
    made = []
    try:
        for name in [source, target]:
            subprocess.run(['createdb', name], env=env, check=True, timeout=30)
            made.append(name)
        with psycopg.connect(host='127.0.0.1', port=5432, user='nexora', password=password, dbname=source) as conn:
            conn.execute('CREATE TABLE restore_probe (value integer PRIMARY KEY, note text)')
            conn.execute("INSERT INTO restore_probe SELECT n, repeat('QA archive corruption ', 20) FROM generate_series(1,100) n")
        archive = tmp_path / 'source.dump'
        subprocess.run(['pg_dump', '-Fc', '--compress=0', '--file', str(archive), source],
                       env=env, check=True, timeout=30)
        archive.write_bytes(archive.read_bytes()[:-64])
        subprocess.run(['pg_restore', '--list', str(archive)], check=True, stdout=subprocess.DEVNULL)
        key = os.urandom(32)
        encrypted = tmp_path / 'source.s4penc'
        backup.encrypt_file(archive, encrypted, key)

        class CorruptArchiveTransport:
            def download_file(self, bucket, object_key, filename):
                Path(filename).write_bytes(encrypted.read_bytes())

        monkeypatch.setattr(backup, 's3_client', lambda: (CorruptArchiveTransport(), 'qa-only'))
        monkeypatch.setenv('S4P_BACKUP_AES_KEY_B64', base64.b64encode(key).decode())
        monkeypatch.setenv('DATABASE_URL', f'postgresql+psycopg://nexora:{password}@127.0.0.1:5432/{source}')
        with pytest.raises(subprocess.CalledProcessError):
            backup.restore_verify_local_only('deliberately-corrupt-qa-archive',
                f'postgresql+psycopg://nexora:{password}@127.0.0.1:5432/{target}')
        with psycopg.connect(host='127.0.0.1', port=5432, user='nexora', password=password, dbname=target) as conn:
            assert conn.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public'").fetchone()[0] == 0
        with psycopg.connect(host='127.0.0.1', port=5432, user='nexora', password=password, dbname=source) as conn:
            assert conn.execute('SELECT count(*) FROM restore_probe').fetchone()[0] == 100
    finally:
        for name in reversed(made):
            subprocess.run(['dropdb', name], env=env, check=True, timeout=30)
