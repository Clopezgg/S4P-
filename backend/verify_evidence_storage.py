#!/usr/bin/env python3
"""Credentialed, private Supabase evidence bridge smoke: write/verify/delete.

Never writes ERP business records. A unique PDF marker is removed even if
the download integrity check fails. Can be run at startup when explicitly
enabled, or manually inside a trusted backend container.
"""
import secrets
import sys

from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import ContentSettings

from app.core.config import get_settings
from app.integrations.azure_blob import get_evidence_container_client


def main() -> int:
    settings = get_settings()
    if settings.evidence_backend not in {"supabase_edge", "supabase"}:
        print("NOT READY: private evidence backend is not configured", file=sys.stderr)
        return 2

    container = get_evidence_container_client(settings)
    container.get_container_properties()

    key = f"__s4p_storage_smoke__/{secrets.token_hex(16)}.pdf"
    payload = (
        b"%PDF-1.4\\n1 0 obj<</Type/Catalog>>endobj\\n"
        + secrets.token_bytes(64).hex().encode("ascii")
        + b"\\n%%EOF\\n"
    )
    wrote = False
    try:
        container.upload_blob(
            name=key, data=payload, overwrite=False,
            content_settings=ContentSettings(content_type="application/pdf"),
        )
        wrote = True
        data = b"".join(container.download_blob(key).chunks())
        if data != payload:
            raise RuntimeError("Private evidence integrity mismatch")
    finally:
        if wrote:
            container.delete_blob(key)
    try:
        container.download_blob(key)
    except ResourceNotFoundError:
        pass
    else:
        raise RuntimeError("Private evidence deletion not confirmed")

    print("PASS: private evidence backend upload/download/delete verified", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
