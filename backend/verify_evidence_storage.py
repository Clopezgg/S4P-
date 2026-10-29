#!/usr/bin/env python3
"""Read/write/delete smoke for the configured *private* Supabase evidence S3 bucket.

Run in the existing Render backend runtime with secret env vars set.
Only writes a random marker; never touches ERP business records or finance tables.
"""
import os
import secrets
import sys
from app.core.config import get_settings
from app.integrations.azure_blob import get_evidence_container_client

def main():
    settings = get_settings()
    if settings.evidence_backend != "supabase":
        print("NOT READY: EVIDENCE_BACKEND is not supabase", file=sys.stderr)
        return 2
    bucket = get_evidence_container_client(settings)
    bucket.get_container_properties()
    marker = f"__s4p_storage_smoke__/{secrets.token_hex(16)}.bin"
    payload = secrets.token_bytes(2048)
    wrote = False
    try:
        bucket.upload_blob(name=marker, data=payload, overwrite=False)
        wrote = True
        received = b"".join(bucket.download_blob(marker).chunks())
        if received != payload:
            raise RuntimeError("Evidence storage integrity mismatch")
    finally:
        if wrote:
            bucket.delete_blob(marker)
    print("PASS: private evidence S3 bucket was accessible; random object uploaded, verified, deleted")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
