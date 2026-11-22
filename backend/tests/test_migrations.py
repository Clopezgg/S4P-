import os
import re
import shutil
import subprocess
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[1]
_worktree_slug = re.sub(
    r"[^a-z0-9]+", "_", os.path.basename(os.path.dirname(os.getcwd())).lower()
).strip("_") or "default"
_DB_NAME = f"nexora_migrations_test_{_worktree_slug}"
_PG_USER = "nexora"
_PG_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "nexora")
_PG_HOST = "localhost"
_PG_PORT = "5432"


_ALEMBIC_BIN = shutil.which("alembic") or str(_BACKEND_DIR / ".venv" / "bin" / "alembic")


def _pg_env() -> dict:
    return {**os.environ, "PGPASSWORD": _PG_PASSWORD, "PGHOST": _PG_HOST, "PGPORT": _PG_PORT, "PGUSER": _PG_USER}


def _run_alembic(*args: str) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "DATABASE_URL": f"postgresql+psycopg://{_PG_USER}:{_PG_PASSWORD}@{_PG_HOST}:{_PG_PORT}/{_DB_NAME}",
        "BOOTSTRAP_ADMIN_EMAIL": "",
        "BOOTSTRAP_ADMIN_PASSWORD": "",
        "FRONTEND_URL": "http://localhost:5173",
        "APP_ENV": "test",
    }
    return subprocess.run(
        [str(_ALEMBIC_BIN), *args],
        cwd=_BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_fresh_install_then_safe_downgrade_preserves_obligations():
    """Verify the reversible boundary without destroying off-ledger payment evidence.

    Revision 742fbe13c921 intentionally retains obligation tables on downgrade.
    Downgrading all the way to base would fail when the currencies table is
    dropped, and a CASCADE would destroy financial evidence. Test the supported
    head -> previous revision transition on an isolated database.
    """
    subprocess.run(["dropdb", "--if-exists", _DB_NAME], check=True, env=_pg_env())
    subprocess.run(["createdb", _DB_NAME], check=True, env=_pg_env())
    try:
        upgrade_to_head = _run_alembic("upgrade", "head")
        assert upgrade_to_head.returncode == 0, upgrade_to_head.stderr

        status_width = subprocess.run(
            ["psql", "-X", "-A", "-t", "--dbname", _DB_NAME, "-c",
             "SELECT character_maximum_length FROM information_schema.columns "
             "WHERE table_schema='public' AND table_name='customer_invoices' AND column_name='status'"],
            env=_pg_env(), capture_output=True, text=True, check=True,
        )
        assert status_width.stdout.strip() == "32"

        downgrade_to_base = _run_alembic("downgrade", "9083ca4ebf44")
        assert downgrade_to_base.returncode == 0, downgrade_to_base.stderr

        retained = subprocess.run(
            ["psql", "-X", "-A", "-t", "--dbname", _DB_NAME, "-c",
             "SELECT to_regclass('public.obligation_plans'), "
             "to_regclass('public.obligation_settlements')"],
            env=_pg_env(), capture_output=True, text=True, check=True,
        )
        assert retained.stdout.strip() == "obligation_plans|obligation_settlements"

        current = _run_alembic("current")
        assert current.returncode == 0, current.stderr
        assert "9083ca4ebf44" in current.stdout
    finally:
        subprocess.run(["dropdb", "--if-exists", _DB_NAME], check=True, env=_pg_env())
