from __future__ import annotations

import json
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
)


def _user_id(request: Request) -> str:
    user = get_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    # Prefer stable email; fallback to sub or name
    return (user.get("email") or user.get("sub") or user.get("name") or "anon").strip()


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _doc_blob(uid: str, api_id: str) -> str:
    return f"{uid}/{api_id}/doc.json"


def _image_blob(uid: str, api_id: str, ext: str) -> str:
    if ext and not ext.startswith("."):
        ext = "." + ext
    ext = (ext or ".png").lower()[:16]
    return f"{uid}/{api_id}/image{ext}"


class Rect(BaseModel):
    id: str
    name: str = ""
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(ge=0, le=1)
    h: float = Field(ge=0, le=1)
    extract_text: bool = True
    diacritics: bool = False
    # Horizontal separators inside the rectangle (0..1 from top)
    seps: List[float] = Field(default_factory=list)


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
    blob_name = _doc_blob(uid, api_id)
    try:
        raw = download_bytes(blob_name)
    except Exception:
        raise HTTPException(status_code=404, detail="API not found")
    return json.loads(raw.decode("utf-8"))


def _save_api(doc: Dict[str, Any]) -> None:
    uid = doc["user_id"]
    api_id = doc["id"]
    blob_name = _doc_blob(uid, api_id)
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
        it["image_url"] = f"/builder/images/{it.get('id')}"
        it.pop("rects", None)
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
    # Extract extension if present
    ext = ""
    if image.filename and "." in image.filename:
        ext = image.filename.rsplit(".", 1)[-1]
    img_blob = _image_blob(uid, api_id, ext)

    # Upload image to GCS
    upload_fileobj(image.file, img_blob, content_type=content_type or None)

    now = _now_iso()
    doc: Dict[str, Any] = {
        "id": api_id,
        "user_id": uid,
        "name": (name or "Untitled API").strip() or "Untitled API",
        "created_at": now,
        "updated_at": now,
        "image_blob": img_blob,
        "rects": [],
    }
    _save_api(doc)

    doc["image_url"] = f"/builder/images/{api_id}"
    return doc


@router.get("/apis/{api_id}")
def get_api(api_id: str, request: Request):
    uid = _user_id(request)
    doc = _load_api(uid, api_id)
    if doc.get("user_id") != uid:
        raise HTTPException(status_code=403, detail="Forbidden")
    doc["image_url"] = f"/builder/images/{api_id}"
    return doc


class ApiUpdate(BaseModel):
    name: Optional[str] = None
    rects: Optional[List[Rect]] = None


@router.put("/apis/{api_id}")
def update_api(api_id: str, upd: ApiUpdate, request: Request):
    uid = _user_id(request)
    doc = _load_api(uid, api_id)
    if doc.get("user_id") != uid:
        raise HTTPException(status_code=403, detail="Forbidden")

    changed = False
    if upd.name is not None:
        doc["name"] = (upd.name or "").strip() or doc.get("name") or "Untitled API"
        changed = True
    if upd.rects is not None:
        # Coerce to plain dicts
        doc["rects"] = [r.model_dump() if isinstance(r, Rect) else r for r in upd.rects]
        changed = True

    if changed:
        doc["updated_at"] = _now_iso()
        _save_api(doc)

    doc["image_url"] = f"/builder/images/{api_id}"
    return doc


@router.delete("/apis/{api_id}")
def delete_api(api_id: str, request: Request):
    uid = _user_id(request)
    # Ensure it exists and belongs to user
    doc = _load_api(uid, api_id)
    if doc.get("user_id") != uid:
        raise HTTPException(status_code=403, detail="Forbidden")
    # Remove all blobs under the API folder
    delete_prefix(f"{uid}/{api_id}/")
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
    return Response(content=data, media_type=ctype)
