#!/usr/bin/env python3
"""Compare original NEXORA source with S4P for missing or modified business files.

This gate protects source parity, not runtime equivalence. Intentional migration
adapters are reviewed in an explicit allowlist.
"""
from __future__ import annotations

import hashlib
import pathlib
import sys

SOURCE = pathlib.Path("/tmp/nexora-parity-source")
TARGET = pathlib.Path(".")
SOURCE_SHA = "2ca980446654f3c92e3ddb1e8f55d847ef073968"
# Original source from upstream NEXORA at migration; set the baseline commit
# in the GitHub workflow to avoid silently accepting future source changes.
ALLOW_CHANGED = {
    "backend/app/api/routes/health.py",
    "backend/app/api/security_headers.py",
    "backend/app/core/config.py",
    "backend/app/core/database.py",
    "backend/app/integrations/azure_blob.py",
    "backend/app/main.py",
    "backend/app/services/evidence_service.py",
    "backend/requirements.txt",
    "backend/tests/test_auth.py",
    "backend/tests/test_cash_flow_actual.py",
    "backend/tests/test_config_hardening.py",
    "backend/tests/test_edit_access.py",
    "frontend/src/pages/LoginPage.tsx",
    "frontend/tests/LoginPage.test.tsx",
}
# Theme source MUST remain identical to original; changing the default breaks
# the original navigation and settings tests across all UI families.
IGNORED_PREFIXES = (".github/workflows/",)
IGNORED_PATHS = {"README.md"}

def fingerprint(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main() -> int:
    missing: list[str] = []
    unexpected: list[str] = []
    changed: list[str] = []
    for src in SOURCE.rglob("*"):
        if not src.is_file() or ".git" in src.parts:
            continue
        rel = src.relative_to(SOURCE).as_posix()
        if rel in IGNORED_PATHS or rel.startswith(IGNORED_PREFIXES):
            continue
        if not (rel.startswith("frontend/") or rel.startswith("backend/") or rel.startswith("brand/")):
            continue
        dst = TARGET / rel
        if not dst.exists():
            missing.append(rel)
        elif fingerprint(src) != fingerprint(dst):
            changed.append(rel)
            if rel not in ALLOW_CHANGED:
                unexpected.append(rel)
    print(f"Original commit: {SOURCE_SHA}")
    print(f"Missing source files: {len(missing)}")
    print(f"Changed source files (expected adapters/tests): {len(changed)}")
    print(f"Unexpectedly changed source files: {len(unexpected)}")
    if missing:
        print("MISSING:", *missing[:40], sep="\n  ")
    if unexpected:
        print("UNAPPROVED CHANGES:", *unexpected[:40], sep="\n  ")
    if missing or unexpected:
        return 1
    print("PASS: original NEXORA application, brand assets and tests preserved.")
    print("NOTE: pass does not certify production behavior, credentials, storage or data.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
