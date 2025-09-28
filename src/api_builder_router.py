from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi import Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from src.login_logic import get_user
from src.gcs_storage import (
    upload_fileobj,
    upload_bytes,
    download_bytes,
    iter_user_docs,
    delete_prefix,
    is_name_taken,
    find_doc_by_id,
    copy_blob,
    signed_url,
)
OBJECT_APIS_BASE_URL = os.getenv("OBJECT_APIS_BASE_URL", "http://localhost:9001")


def _object_api_url(doc: Dict[str, Any]) -> str:
    base = (OBJECT_APIS_BASE_URL or "").rstrip("/")
    api_name = doc.get("name") or doc.get("id") or ""
    if base:
        return f"{base}/api/{api_name}"
    return f"/external/apis/by-name/{api_name}"


def _user_id(request: Request) -> str:
    user = get_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    # Prefer stable email; fallback to sub or name
    return (user.get("email") or user.get("sub") or user.get("name") or "anon").strip()


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _doc_blob_by_name(uid: str, api_name: str) -> str:
    return f"{uid}/{api_name}/doc.json"


def _image_blob_by_name(uid: str, api_name: str, ext: str) -> str:
    if ext and not ext.startswith("."):
        ext = "." + ext
    ext = (ext or ".png").lower()[:16]
    return f"{uid}/{api_name}/image{ext}"


def _random_name(n: int = 10) -> str:
    import base64, os as _os
    token = base64.urlsafe_b64encode(_os.urandom(9)).decode("ascii").rstrip("=")
    return token[:max(4, n)]


class Rect(BaseModel):
    id: str
    name: str = ""
    x: float = Field(ge=0, le=1)
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(ge=1)
    h: int = Field(ge=1)
    # Horizontal separators inside the rectangle (pixels from top)
    seps: List[int] = Field(default_factory=list)

    # Flag to control text extraction
    extract_text: bool = True

    

class ApiMeta(BaseModel):
    id: str
    user_id: str
    name: str = "Untitled API"
    created_at: str
    updated_at: str
    image_blob: str  # gs blob where the image is stored
    image_url: Optional[str] = None  # computed on read
    rects: List[Rect] = Field(default_factory=list)


def _load_api(uid: str, api_id: str) -> Dict[str, Any]:
    found = find_doc_by_id(uid, api_id)
    if not found:
        raise HTTPException(status_code=404, detail="API not found")
    doc, _ = found
    return doc


def _save_api(doc: Dict[str, Any]) -> None:
    uid = doc["user_id"]
    name = doc["name"]
    blob_name = _doc_blob_by_name(uid, name)
    data = json.dumps(doc, ensure_ascii=False, indent=2).encode("utf-8")
    upload_bytes(data, blob_name, content_type="application/json")


def _list_user_apis(uid: str) -> List[Dict[str, Any]]:
    return list(iter_user_docs(uid))


router = APIRouter(prefix="/builder", tags=["builder"])


@router.get("/health")
def health():
    return {"ok": True}


@router.get("/apis")
def list_apis(request: Request):
    uid = _user_id(request)
    items = _list_user_apis(uid)
    # Attach image_url and strip heavy fields for list view
    for it in items:
        # Prefer signed URL for faster direct load
        url = None
        try:
            url = signed_url(it.get("image_blob") or "", minutes=20)
        except Exception:
            url = None
        it["image_url"] = url or f"/builder/images/{it.get('id')}"
        it["access_url"] = _object_api_url(it)
        # Keep rects in the payload so the client can cache all docs at load time
    items.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return items


@router.post("/apis")
async def create_api(request: Request, image: UploadFile = File(...), name: Optional[str] = None):
    uid = _user_id(request)

    # Validate image type lightly
    content_type = (image.content_type or "").lower()
    if not (content_type.startswith("image/") or image.filename):
        raise HTTPException(status_code=400, detail="Image file required")

    api_id = uuid.uuid4().hex
    # Create a unique random API name for the folder (ignore provided name)
    attempt = 0
    api_name = None
    while True:
        attempt += 1
        base = _random_name(10)
        candidate = base if attempt == 1 else f"{base}-{_random_name(4)}"
        if not is_name_taken(uid, candidate):
            api_name = candidate
            break

    # Extract extension if present
    ext = ""
    if image.filename and "." in image.filename:
        ext = image.filename.rsplit(".", 1)[-1]
    img_blob = _image_blob_by_name(uid, api_name, ext)

    # Upload image to GCS
    upload_fileobj(image.file, img_blob, content_type=content_type or None)

    now = _now_iso()
    doc: Dict[str, Any] = {
        "id": api_id,
        "user_id": uid,
        "name": api_name,
        "created_at": now,
        "updated_at": now,
        "image_blob": img_blob,
        "rects": [],
    }
    _save_api(doc)

    url = None
    try:
        url = signed_url(img_blob, minutes=20)
    except Exception:
        url = None

    resp = dict(doc)
    resp["image_url"] = url or f"/builder/images/{api_id}"
    resp["access_url"] = _object_api_url(resp)
    return resp


@router.get("/apis/{api_id}")
def get_api(api_id: str, request: Request):
    uid = _user_id(request)
    doc = _load_api(uid, api_id)
    if doc.get("user_id") != uid:
        raise HTTPException(status_code=403, detail="Forbidden")
    url = None
    try:
        url = signed_url(doc.get("image_blob") or "", minutes=20)
    except Exception:
        url = None
    resp = dict(doc)
    resp["image_url"] = url or f"/builder/images/{api_id}"
    resp["access_url"] = _object_api_url(resp)
    return resp


class ApiUpdate(BaseModel):
    name: Optional[str] = None
    rects: Optional[List[Rect]] = None


@router.put("/apis/{api_id}")
def update_api(api_id: str, upd: ApiUpdate, request: Request):
    uid = _user_id(request)
    found = find_doc_by_id(uid, api_id)
    if not found:
        raise HTTPException(status_code=404, detail="API not found")
    doc, old_doc_blob = found
    if doc.get("user_id") != uid:
        raise HTTPException(status_code=403, detail="Forbidden")

    changed = False
    if upd.name is not None:
        new_name = (upd.name or "").strip() or doc.get("name") or ""
        if not new_name:
            new_name = _random_name(10)
        # If name actually changes, ensure uniqueness and move
        if new_name != doc.get("name"):
            base = new_name
            while is_name_taken(uid, new_name):
                # If we are colliding with our current folder, stop
                if new_name == doc.get("name"):
                    break
                new_name = f"{base}-{_random_name(4)}"
            # Move image blob if present
            old_img_blob = doc.get("image_blob") or ""
            ext = ""
            if "." in old_img_blob:
                ext = old_img_blob.rsplit(".", 1)[-1]
            new_img_blob = _image_blob_by_name(uid, new_name, ext)
            if old_img_blob:
                try:
                    copy_blob(old_img_blob, new_img_blob, delete_src=False)
                except Exception:
                    pass
            # Update fields and save new doc.json
            old_prefix = f"{uid}/{doc.get('name')}/"
            doc["name"] = new_name
            doc["image_blob"] = new_img_blob
            doc["updated_at"] = _now_iso()
            _save_api(doc)
            try:
                delete_prefix(old_prefix)
            except Exception:
                pass
            changed = False  # already saved
    if upd.rects is not None:
        # Coerce to plain dicts and ensure pixel values are ints
        pixel_rects = []
        for r in upd.rects:
            if isinstance(r, Rect):
                d = r.model_dump()
            else:
                d = dict(r)
            # Ensure pixel values are ints
            d["x"] = int(round(d.get("x", 0)))
            d["y"] = int(round(d.get("y", 0)))
            d["w"] = int(round(d.get("w", 1)))
            d["h"] = int(round(d.get("h", 1)))
            d["seps"] = [int(round(s)) for s in d.get("seps", [])]
            pixel_rects.append(d)
        doc["rects"] = pixel_rects
        changed = True

    if changed:
        doc["updated_at"] = _now_iso()
        _save_api(doc)

    # Prefer a signed URL for faster reloads post-save
    url = None
    try:
        url = signed_url(doc.get("image_blob") or "", minutes=20)
    except Exception:
        url = None
    resp = dict(doc)
    resp["image_url"] = url or f"/builder/images/{api_id}"
    resp["access_url"] = _object_api_url(resp)
    return resp


@router.delete("/apis/{api_id}")
def delete_api(api_id: str, request: Request):
    uid = _user_id(request)
    # Ensure it exists and belongs to user
    doc = _load_api(uid, api_id)
    if doc.get("user_id") != uid:
        raise HTTPException(status_code=403, detail="Forbidden")
    # Remove all blobs under the API folder
    delete_prefix(f"{uid}/{doc.get('name')}/")
    return {"ok": True}


@router.get("/images/{api_id}")
def fetch_image(api_id: str, request: Request):
    """Proxy the private image from GCS so the browser can display it."""
    uid = _user_id(request)
    doc = _load_api(uid, api_id)
    if doc.get("user_id") != uid:
        raise HTTPException(status_code=403, detail="Forbidden")
    img_blob = doc.get("image_blob") or ""
    try:
        data = download_bytes(img_blob)
    except Exception:
        raise HTTPException(status_code=404, detail="Image not found")
    # Basic content-type guess from extension
    ctype = "image/png"
    if ".jpg" in img_blob or ".jpeg" in img_blob:
        ctype = "image/jpeg"
    elif ".webp" in img_blob:
        ctype = "image/webp"
    elif ".gif" in img_blob:
        ctype = "image/gif"
    # Add a short cache to reduce repeat downloads while editing
    resp = Response(content=data, media_type=ctype)
    resp.headers["Cache-Control"] = "private, max-age=60"
    return resp
