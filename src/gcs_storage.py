from __future__ import annotations

import io
import json
import os
from typing import Any, Dict, Iterable, Optional

from google.cloud import storage
from google.oauth2 import service_account


# Defaults can be overridden via env vars without touching code
DEFAULT_BUCKET = os.getenv("API_STORAGE_BUCKET", "api_information_storage")
DEFAULT_KEYFILE = os.getenv("API_BUCKET_KEY_FILE", "secrets/api_bucket_db_key.json")


def _credentials():
    """
    Return credentials for the storage client. Prefer explicit service-account
    key file (the project ships with `secrets/api_bucket_db_key.json`).
    Fallback to Application Default Credentials if the file is missing.
    """
    path = DEFAULT_KEYFILE
    try:
        if path and os.path.exists(path):
            return service_account.Credentials.from_service_account_file(path)
    except Exception:
        pass
    # Fallback to ADC (e.g., when running on GCP or when GAC is set)
    return None


def storage_client() -> storage.Client:
    creds = _credentials()
    if creds is not None:
        return storage.Client(credentials=creds, project=creds.project_id)
    return storage.Client()  # ADC


def get_bucket(name: Optional[str] = None) -> storage.Bucket:
    client = storage_client()
    bucket_name = name or DEFAULT_BUCKET
    return client.bucket(bucket_name)


def upload_bytes(data: bytes, blob_name: str, *, content_type: Optional[str] = None, cache_seconds: int = 0) -> str:
    bucket = get_bucket()
    blob = bucket.blob(blob_name)
    if cache_seconds:
        blob.cache_control = f"public, max-age={int(cache_seconds)}"
    blob.upload_from_string(data, content_type=content_type)
    return blob.name


def upload_fileobj(fileobj, blob_name: str, *, content_type: Optional[str] = None, cache_seconds: int = 0) -> str:
    data = fileobj.read()
    if hasattr(fileobj, "seek"):
        try:
            fileobj.seek(0)
        except Exception:
            pass
    return upload_bytes(data, blob_name, content_type=content_type, cache_seconds=cache_seconds)


def download_bytes(blob_name: str) -> bytes:
    bucket = get_bucket()
    blob = bucket.blob(blob_name)
    return blob.download_as_bytes()


def delete_prefix(prefix: str) -> int:
    """Delete all blobs under the prefix. Returns count deleted."""
    client = storage_client()
    bucket = get_bucket()
    deleted = 0
    for blob in client.list_blobs(bucket, prefix=prefix):
        try:
            blob.delete()
            deleted += 1
        except Exception:
            pass
    return deleted


def iter_user_docs(uid: str) -> Iterable[Dict[str, Any]]:
    """
    Yield parsed JSON docs for a user by scanning `<uid>/*/doc.json`.
    """
    client = storage_client()
    bucket = get_bucket()
    prefix = f"{uid}/"
    for blob in client.list_blobs(bucket, prefix=prefix):
        name = blob.name or ""
        if not name.endswith("/doc.json"):
            continue
        try:
            raw = blob.download_as_bytes()
            doc = json.loads(raw.decode("utf-8"))
            yield doc
        except Exception:
            # ignore malformed docs
            continue


