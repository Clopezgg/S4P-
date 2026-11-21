"""Security gates for one-way clone; no production connection in unit tests."""
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "pg16_to_aiven_pg17.py"
spec = importlib.util.spec_from_file_location("s4p_pg17_clone", SCRIPT)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
SOURCE = (
    "postgresql+psycopg://ops:secret@"
    "dpg-dbh8j41srm7s73f3u1b0-a.internal:5432/s4p_postgres_staging"
)
TARGET = "postgresql://user:password@pg-service.aivencloud.com:12345/defaultdb?sslmode=verify-full"


def test_rejects_any_other_source_and_destination():
    src, dst = module.parse_connection(SOURCE), module.parse_connection(TARGET)
    module.validate_endpoints(src, dst, "pg-service.aivencloud.com")
    assert src.database == "s4p_postgres_staging"
    assert dst.sslmode == "verify-full"


@pytest.mark.parametrize("target", [
    "postgresql://u:p@pg-service.aivencloud.com/defaultdb?sslmode=require",
    "postgresql://u:p@pg-service.aivencloud.com.evil/defaultdb?sslmode=verify-full",
    "postgresql://u:p@pg-service.aivencloud.com/production?sslmode=verify-full",
])
def test_rejects_unexpected_aiven_target(target):
    with pytest.raises(RuntimeError):
        module.validate_endpoints(
            module.parse_connection(SOURCE),
            module.parse_connection(target), "pg-service.aivencloud.com",
        )


def test_rejects_untrusted_source():
    with pytest.raises(RuntimeError):
        module.validate_endpoints(
            module.parse_connection("postgresql://u:p@localhost/s4p_restore_test"),
            module.parse_connection(TARGET), "pg-service.aivencloud.com",
        )


def test_requires_real_ca_file(tmp_path):
    with pytest.raises(RuntimeError, match="CA certificate"):
        module.pg_environment(module.parse_connection(TARGET), ca_file=str(tmp_path / "missing.pem"))


def test_pg_dump_source_environment_read_only():
    env = module.pg_environment(module.parse_connection(SOURCE), source=True)
    assert env["PGOPTIONS"] == "-c default_transaction_read_only=on"
    assert env["PGDATABASE"] == "s4p_postgres_staging"
