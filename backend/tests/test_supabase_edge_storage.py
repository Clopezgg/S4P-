"""Private Supabase Edge evidence bridge contract: signed requests and no leaks."""
import base64
import hashlib
import json
from io import BytesIO
from urllib.error import HTTPError
from unittest.mock import patch

import pytest
from azure.core.exceptions import ClientAuthenticationError, ResourceExistsError, ResourceNotFoundError
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from app.core.config import Settings
from app.integrations.azure_blob import get_evidence_container_client


URL = "https://klnfxzyccohplnzbdecy.supabase.co/functions/v1/s4p-evidence-bridge"
KEY = "12345678-1234-4234-8234-123456789abc/87654321-1234-4234-8234-abcdef123456-evidence.pdf"


@pytest.fixture
def adapter_and_signer():
    signer = Ed25519PrivateKey.generate()
    raw = signer.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    settings = Settings(
        evidence_backend="supabase_edge",
        evidence_container_name="s4p-evidence-private",
        supabase_edge_bridge_url=URL,
        supabase_edge_signing_key_b64=base64.b64encode(raw).decode(),
    )
    return get_evidence_container_client(settings), signer


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


def check_signature(req, signer):
    headers = {key.casefold(): val for key, val in req.header_items()}
    body = req.data
    canonical = "\n".join(
        (headers["x-s4p-ts"], headers["x-s4p-nonce"], headers["x-s4p-op"],
         headers["x-s4p-key"], headers["x-s4p-mime"], hashlib.sha256(body).hexdigest())
    )
    sig = base64.urlsafe_b64decode(headers["x-s4p-signature"] + "==")
    signer.public_key().verify(sig, canonical.encode())
    assert req.full_url == URL
    assert "secret" not in str(req.header_items()).lower()


def test_edge_bridge_full_contract(adapter_and_signer):
    adapter, signer = adapter_and_signer
    issued = []
    def mock_urlopen(req, timeout):
        check_signature(req, signer)
        assert timeout == 60
        headers = {k.casefold(): v for k, v in req.header_items()}
        op = headers["x-s4p-op"]
        issued.append(op)
        if op == "health":
            return Response(json.dumps({"ok": True, "private": True}).encode())
        if op == "upload":
            assert req.data == b"%PDF-1.4\nbody"
            assert headers["x-s4p-mime"] == "application/pdf"
            return Response(b'{"ok":true}')
        if op == "download":
            return Response(b"%PDF-1.4\nbody")
        if op == "remove":
            return Response(b'{"ok":true}')
        raise AssertionError(op)
    with patch("app.integrations.supabase_edge_storage.urlopen", side_effect=mock_urlopen):
        assert adapter.get_container_properties()["private"]
        from azure.storage.blob import ContentSettings
        adapter.upload_blob(name=KEY, data=b"%PDF-1.4\nbody", content_settings=ContentSettings(content_type="application/pdf"))
        assert b"".join(adapter.download_blob(KEY).chunks()) == b"%PDF-1.4\nbody"
        adapter.delete_blob(KEY)
    assert issued == ["health", "upload", "download", "remove"]


def test_edge_bridge_duplicate_and_missing_errors(adapter_and_signer):
    adapter, _signer = adapter_and_signer
    def duplicate(req, timeout):
        raise HTTPError(URL, 409, "exists", {}, BytesIO(b"internal"))
    with patch("app.integrations.supabase_edge_storage.urlopen", side_effect=duplicate):
        with pytest.raises(ResourceExistsError):
            adapter.upload_blob(name=KEY, data=b"%PDF", overwrite=False)
    def missing(req, timeout):
        raise HTTPError(URL, 404, "missing", {}, BytesIO(b"internal"))
    with patch("app.integrations.supabase_edge_storage.urlopen", side_effect=missing):
        with pytest.raises(ResourceNotFoundError):
            adapter.download_blob(KEY)


def test_edge_bridge_rejects_unsigned_or_non_https_configurations():
    for kwargs in (
        {"supabase_edge_bridge_url": "http://example.com/functions/v1/s4p-evidence-bridge"},
        {"supabase_edge_bridge_url": URL, "supabase_edge_signing_key_b64": ""},
    ):
        with pytest.raises(ValueError, match="Supabase Edge"):
            Settings(evidence_backend="supabase_edge", evidence_container_name="s4p-evidence-private", **kwargs)
