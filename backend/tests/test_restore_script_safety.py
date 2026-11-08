"""The operational shell restore must reject unsafe targets before any PG call."""
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "db_restore.sh"


@pytest.mark.parametrize("overrides,target", [
    ({"PGHOST": "production.example"}, "s4p_restore_qa"),
    ({"PGHOST": "localhost"}, "production"),
    ({"PGHOST": "localhost"}, "postgresql://remote/s4p_restore_qa"),
    ({"PGHOST": "localhost", "PGHOSTADDR": "192.0.2.1"}, "s4p_restore_qa"),
    ({"PGHOST": "localhost", "PGSERVICE": "production"}, "s4p_restore_qa"),
    ({"PGHOST": "localhost", "PGSERVICEFILE": "/tmp/service"}, "s4p_restore_qa"),
])
def test_unsafe_shell_restore_never_invokes_postgres(tmp_path, overrides, target):
    marker = tmp_path / "pg-called"
    for command in ("dropdb", "createdb", "pg_restore"):
        stub = tmp_path / command
        stub.write_text(f'#!/bin/sh\ntouch "{marker}"\nexit 91\n')
        stub.chmod(0o755)
    dump = tmp_path / "backup.dump"
    dump.write_bytes(b"not read for rejected targets")
    env = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
    env.update(overrides, PATH=f"{tmp_path}:/usr/bin:/bin")
    result = subprocess.run(
        ["bash", str(SCRIPT), str(dump), target], env=env,
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 1, result.stderr
    assert not marker.exists()
