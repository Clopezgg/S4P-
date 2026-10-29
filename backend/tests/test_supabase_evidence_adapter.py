"""Verify Supabase private S3 adapter against a deterministic in-memory client.

These tests do not claim a live Supabase upload; a credentialed production
upload/download smoke is a separate release gate.
"""
from io import BytesIO
from unittest.mock import patch

import pytest
from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from botocore.exceptions import ClientError

from app.core.config import Settings
from app.integrations.supabase_storage import SupabaseEvidenceContainer


class FakeStorage:
    def __init__(self):
        self.objects = {}
    def head_bucket(self, **kwargs):
        assert kwargs["Bucket"] == "s4p-evidence-private"
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}
    def head_object(self, **kwargs):
        key = kwargs["Key"]
        if key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}, "ResponseMetadata": {"HTTPStatusCode": 404}}, "HeadObject")
        return {}
    def put_object(self, **kwargs):
        self.objects[kwargs["Key"]] = kwargs["Body"]
        return {"ETag": "fake"}
    def get_object(self, **kwargs):
        key = kwargs["Key"]
        if key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}, "ResponseMetadata": {"HTTPStatusCode": 404}}, "GetObject")
        return {"Body": FakeBody(self.objects[key])}
    def delete_object(self, **kwargs):
        self.objects.pop(kwargs["Key"], None)
        return {}


class FakeBody:
    def __init__(self, data):
        self.file = BytesIO(data)
    def iter_chunks(self, chunk_size):
        while block := self.file.read(chunk_size):
            yield block
    def close(self):
        self.file.close()


@pytest.fixture
def storage():
    fake = FakeStorage()
    settings = Settings(
        evidence_backend="supabase",
        evidence_container_name="s4p-evidence-private",
        supabase_s3_endpoint="https://project.storage.supabase.co/storage/v1/s3",
        supabase_s3_region="us-east-1",
        supabase_s3_access_key_id="test-only",
        supabase_s3_secret_access_key="test-only",
    )
    with patch("boto3.client", return_value=fake):
        return SupabaseEvidenceContainer(settings)


def test_private_container_roundtrip_and_delete(storage):
    assert storage.get_container_properties()
    storage.upload_blob(name="company/doc.pdf", data=b"%PDF-demo", overwrite=False)
    assert b"".join(storage.download_blob("company/doc.pdf").chunks()) == b"%PDF-demo"
    with pytest.raises(ResourceExistsError):
        storage.upload_blob(name="company/doc.pdf", data=b"changed", overwrite=False)
    storage.delete_blob("company/doc.pdf")
    with pytest.raises(ResourceNotFoundError):
        storage.download_blob("company/doc.pdf")


def test_storage_transport_errors_do_not_return_secret_or_public_url(storage):
    with pytest.raises(ResourceNotFoundError):
        storage.download_blob("private/absent.jpg")
