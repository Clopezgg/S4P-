"""Enforce fail-closed Render schema checks; never mutate production on boot."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_render_boot_does_not_run_schema_migrations():
    dockerfile = (REPO_ROOT / "Dockerfile.render").read_text(encoding="utf-8")
    startup = dockerfile.split("\nCMD [", 1)[1]
    assert "alembic current --check-heads &&" in startup
    assert "alembic upgrade" not in startup
    assert startup.index("alembic current --check-heads") < startup.index("uvicorn")


def test_alembic_floor_supports_read_only_head_check():
    requirements = (REPO_ROOT / "backend" / "requirements.txt").read_text(encoding="utf-8")
    assert "alembic>=1.17.1,<2" in requirements
