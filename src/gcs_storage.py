from __future__ import annotations

import io
import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

from google.cloud import storage
from google.oauth2 import service_account
from datetime import timedelta


# Defaults can be overridden via env vars without touching code
DEFAULT_BUCKET = os.getenv("API_STORAGE_BUCKET", "api_information_storage")
DEFAULT_KEYFILE = os.getenv("API_BUCKET_KEY_FILE", "secrets/api_bucket_db_key.json")
LOCAL_STORAGE_DIR = Path(__file__).resolve().parents[1] / "local_storage"


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
    if os.environ["API_STORAGE_MODE"] == "local":
        path = LOCAL_STORAGE_DIR / blob_name.lstrip("/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return blob_name
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
    if os.environ["API_STORAGE_MODE"] == "local":
        path = LOCAL_STORAGE_DIR / blob_name.lstrip("/")
        return path.read_bytes()
    bucket = get_bucket()
    blob = bucket.blob(blob_name)
    return blob.download_as_bytes()


def delete_prefix(prefix: str) -> int:
    """Delete all blobs under the prefix. Returns count deleted."""
    if os.environ["API_STORAGE_MODE"] == "local":
        target = LOCAL_STORAGE_DIR / prefix.lstrip("/")
        if target.is_file():
            target.unlink()
            return 1
        if not target.exists():
            return 0
        if target.is_dir():
            deleted = sum(1 for path in target.rglob("*") if path.is_file())
            shutil.rmtree(target)
            return deleted
        return 0
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


def blob_exists(blob_name: str) -> bool:
    if os.environ["API_STORAGE_MODE"] == "local":
        return (LOCAL_STORAGE_DIR / blob_name.lstrip("/")).is_file()
    bucket = get_bucket()
    return bucket.blob(blob_name).exists(storage_client())


def is_name_taken(uid: str, name: str) -> bool:
    """Return True if any object exists under `<uid>/<name>/` prefix."""
    if os.environ["API_STORAGE_MODE"] == "local":
        prefix_path = LOCAL_STORAGE_DIR / uid / name
        if prefix_path.is_file():
            return True
        if prefix_path.is_dir():
            return any(path.is_file() for path in prefix_path.rglob("*"))
        return False
    client = storage_client()
    bucket = get_bucket()
    prefix = f"{uid}/{name}/"
    it = client.list_blobs(bucket, prefix=prefix, max_results=1)
    for _ in it:
        return True
    return False


def copy_blob(src_blob: str, dst_blob: str, *, delete_src: bool = False) -> None:
    if os.environ["API_STORAGE_MODE"] == "local":
        src = LOCAL_STORAGE_DIR / src_blob.lstrip("/")
        dst = LOCAL_STORAGE_DIR / dst_blob.lstrip("/")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        if delete_src:
            try:
                src.unlink()
            except FileNotFoundError:
                pass
        return
    bucket = get_bucket()
    src = bucket.blob(src_blob)
    bucket.copy_blob(src, bucket, dst_blob)
    if delete_src:
        try:
            src.delete()
        except Exception:
            pass


def iter_user_docs(uid: str) -> Iterable[Dict[str, Any]]:
    """
    Yield parsed JSON docs for a user by scanning `<uid>/*/bboxes.json`.
    """
    if os.environ["API_STORAGE_MODE"] == "local":
        user_root = LOCAL_STORAGE_DIR / uid
        if not user_root.exists():
            return
        for path in user_root.rglob("bboxes.json"):
            if not path.is_file():
                continue
            try:
                raw = path.read_bytes()
                doc = json.loads(raw.decode("utf-8"))
                yield doc
            except Exception:
                continue
        return
    client = storage_client()
    bucket = get_bucket()
    prefix = f"{uid}/"
    for blob in client.list_blobs(bucket, prefix=prefix):
        name = blob.name or ""
        if not name.endswith("/bboxes.json"):
            continue
        try:
            raw = blob.download_as_bytes()
            doc = json.loads(raw.decode("utf-8"))
            yield doc
        except Exception:
            # ignore malformed docs
            continue


def find_doc_by_id(uid: str, api_id: str) -> Optional[Tuple[Dict[str, Any], str]]:
    """Return (doc, blob_name) for the given id within user's folder."""
    if os.environ["API_STORAGE_MODE"] == "local":
        user_root = LOCAL_STORAGE_DIR / uid
        if not user_root.exists():
            return None
        for path in user_root.rglob("bboxes.json"):
            if not path.is_file():
                continue
            try:
                raw = path.read_bytes()
                doc = json.loads(raw.decode("utf-8"))
                if str(doc.get("id")) == str(api_id):
                    return doc, path.relative_to(LOCAL_STORAGE_DIR).as_posix()
            except Exception:
                continue
        return None
    client = storage_client()
    bucket = get_bucket()
    prefix = f"{uid}/"
    for blob in client.list_blobs(bucket, prefix=prefix):
        name = blob.name or ""
        if not name.endswith("/bboxes.json"):
            continue
        try:
            raw = blob.download_as_bytes()
            doc = json.loads(raw.decode("utf-8"))
            if str(doc.get("id")) == str(api_id):
                return doc, name
        except Exception:
            continue
    return None


def find_doc_by_name(uid: str, api_name: str) -> Optional[Tuple[Dict[str, Any], str]]:
    """Return (doc, blob_name) for the given API folder name."""
    if os.environ["API_STORAGE_MODE"] == "local":
        path = LOCAL_STORAGE_DIR / uid / api_name / "bboxes.json"
        if not path.is_file():
            return None
        try:
            raw = path.read_bytes()
            doc = json.loads(raw.decode("utf-8"))
            return doc, path.relative_to(LOCAL_STORAGE_DIR).as_posix()
        except Exception:
            return None
    client = storage_client()
    bucket = get_bucket()
    blob_name = f"{uid}/{api_name}/bboxes.json"
    blob = bucket.blob(blob_name)
    if not blob.exists(client):
        return None
    try:
        raw = blob.download_as_bytes()
        doc = json.loads(raw.decode("utf-8"))
        return doc, blob_name
    except Exception:
        return None


def signed_url(blob_name: str, minutes: int = 15) -> Optional[str]:
    """Generate a V4 signed URL for GET; return None on failure."""
    if os.environ["API_STORAGE_MODE"] == "local":
        return None
    try:
        bucket = get_bucket()
        blob = bucket.blob(blob_name)
        return blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=max(1, int(minutes))),
            method="GET",
        )
    except Exception:
        return None
