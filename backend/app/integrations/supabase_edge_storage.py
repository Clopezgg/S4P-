"""Ed25519-authenticated private Supabase Edge Storage bridge.

The Supabase service-role/secret key never leaves the Supabase project. Only
the Render backend receives the signing private key. Access to this adapter
is governed by the unchanged NEXORA FastAPI RBAC before any upload/download.
"""
from __future__ import annotations

import base64
import hashlib
import io
import secrets
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from azure.core.exceptions import (
    ClientAuthenticationError,
    HttpResponseError,
    ResourceExistsError,
    ResourceNotFoundError,
    ServiceRequestError,
)
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core.config import Settings


class _Download:
    def __init__(self, payload: bytes):
        self.payload = payload

    def chunks(self):
        stream = io.BytesIO(self.payload)
        while chunk := stream.read(64 * 1024):
            yield chunk


class SupabaseEdgeEvidenceContainer:
    """Preserve the existing Azure-like private evidence storage contract."""

    def __init__(self, settings: Settings):
        self.endpoint = settings.supabase_edge_bridge_url.rstrip("/")
        self.bucket = settings.evidence_container_name
        key = base64.b64decode(settings.supabase_edge_signing_key_b64, validate=True)
        if len(key) != 32:
            raise ValueError("Supabase Edge signing key must contain 32 bytes")
        self.signer = Ed25519PrivateKey.from_private_bytes(key)

    def _request(self, op: str, *, name: str = "", data: bytes = b"", mime: str = "") -> bytes:
        stamp = str(int(time.time()))
        nonce = secrets.token_hex(16)
        digest = hashlib.sha256(data).hexdigest()
        canonical = "\n".join((stamp, nonce, op, name, mime, digest))
        signature = base64.urlsafe_b64encode(
            self.signer.sign(canonical.encode("utf-8"))
        ).rstrip(b"=").decode("ascii")
        headers = {
            "Content-Type": "application/octet-stream",
            "X-S4P-Ts": stamp,
            "X-S4P-Nonce": nonce,
            "X-S4P-Signature": signature,
            "X-S4P-Op": op,
            "X-S4P-Key": name,
            "X-S4P-Mime": mime,
            "Cache-Control": "no-store",
        }
        req = Request(self.endpoint, data=data, headers=headers, method="POST")
        try:
            with urlopen(req, timeout=60) as response:
                return response.read()
        except HTTPError as exc:
            # Always close failed HTTP responses and discard provider details,
            # since they could include internal storage metadata.
            code = exc.code
            exc.close()
            if code == 404:
                raise ResourceNotFoundError("Private evidence object not found") from exc
            if code == 409:
                raise ResourceExistsError("Private evidence object already exists") from exc
            if code in (401, 403):
                raise ClientAuthenticationError("Private evidence bridge authentication failed") from exc
            response_error = HttpResponseError(message="Private evidence bridge unavailable")
            response_error.status_code = code
            raise response_error from exc
        except (TimeoutError, URLError, OSError) as exc:
            raise ServiceRequestError("Private evidence bridge connection failed") from exc

    def get_container_properties(self):
        import json

        result = json.loads(self._request("health"))
        if result.get("ok") is not True or result.get("private") is not True:
            raise ServiceRequestError("Private evidence bucket is not ready")
        return {"private": True}

    def upload_blob(self, *, name: str, data: bytes, overwrite: bool = False, content_settings=None):
        if overwrite:
            raise ValueError("Evidence objects may not be overwritten")
        mime = getattr(content_settings, "content_type", None) or "application/octet-stream"
        self._request("upload", name=name, data=data, mime=mime)

    def download_blob(self, name: str):
        return _Download(self._request("download", name=name))

    def delete_blob(self, name: str):
        self._request("remove", name=name)
