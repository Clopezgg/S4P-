#!/usr/bin/env python3
"""Fail CI when the retired platform name is visible in current product source.

Historical provider IDs, keys and persisted integration protocols are explicitly
allowed until a tested compatibility migration is available. Client legal names
are not treated as platform identities.
"""
from __future__ import annotations
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCAN = [ROOT / "frontend/src", ROOT / "frontend/index.html", ROOT / "frontend/vite.config.ts",
        ROOT / "backend/app/api/routes/treasury.py", ROOT / "backend/app/services/voucher_service.py",
        ROOT / "backend/app/services/report_export_service.py"]
PATTERN = re.compile(r"nexora", re.I)
LEGACY = re.compile(
    r"nexora[:._-]|x-nexora-edit-access|nexora_session|nexora_dev|"
    r"nexora@localhost|nexora\.group|nexora\.hn|constructora nexora|torre nexora",
    re.I,
)
SKIP_EXT = {".png", ".jpg", ".jpeg", ".pdf", ".webp", ".ico", ".woff", ".woff2"}
violations = []
legacy = 0
for target in SCAN:
    paths = target.rglob("*") if target.is_dir() else [target]
    for path in paths:
        if not path.is_file() or path.suffix.lower() in SKIP_EXT:
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeError:
            continue
        for i, line in enumerate(lines, 1):
            if not PATTERN.search(line):
                continue
            if LEGACY.search(line):
                legacy += 1
            else:
                violations.append(f"{path.relative_to(ROOT)}:{i}: {line.strip()[:180]}")
if violations:
    print("ERROR: old platform brand survives in product-facing source:")
    print("\n".join(violations))
    sys.exit(1)
print(f"S4P brand audit passed. {legacy} technical/tenant references retained for compatibility.")
