"""Fail-closed checks for restoring a REAL backup into a local disposable DB only."""
from __future__ import annotations

from importlib import import_module
import subprocess
import sys
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
