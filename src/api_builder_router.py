from __future__ import annotations

import json
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi import Request
from pydantic import BaseModel, Field

from src.login_logic import get_user


DATA_DIR = Path("secrets/api_builder")
IMAGES_DIR = DATA_DIR / "images"
APIS_DIR = DATA_DIR / "apis"


def _ensure_dirs():
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    APIS_DIR.mkdir(parents=True, exist_ok=True)


def _user_id(request: Request) -> str:
    user = get_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    # Prefer stable email; fallback to sub or name
    return (user.get("email") or user.get("sub") or user.get("name") or "anon").strip()


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


class Rect(BaseModel):
    id: str
    name: str = ""
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(ge=0, le=1)
    h: float = Field(ge=0, le=1)
    extract_text: bool = True


class ApiMeta(BaseModel):
    id: str
    user_id: str
    name: str = "Untitled API"
    created_at: str
    updated_at: str
    image_filename: str  # stored filename under IMAGES_DIR
    image_url: Optional[str] = None  # computed on read
    rects: List[Rect] = Field(default_factory=list)


def _api_path(api_id: str) -> Path:
    return APIS_DIR / f"{api_id}.json"


def _load_api(api_id: str) -> Dict[str, Any]:
    p = _api_path(api_id)
    if not p.exists():
        raise HTTPException(status_code=404, detail="API not found")
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def _save_api(doc: Dict[str, Any]) -> None:
    p = _api_path(doc["id"])  # type: ignore[index]
    tmp = p.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    tmp.replace(p)


def _list_user_apis(uid: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for fp in sorted(APIS_DIR.glob("*.json")):
        try:
            with fp.open("r", encoding="utf-8") as f:
                j = json.load(f)
            if j.get("user_id") == uid:
                items.append(j)
        except Exception:
            continue
    return items


router = APIRouter(prefix="/builder", tags=["builder"])


@router.get("/health")
def health():
    return {"ok": True}


@router.get("/apis")
def list_apis(request: Request):
    _ensure_dirs()
    uid = _user_id(request)
    items = _list_user_apis(uid)
    # Attach image_url for convenience
    for it in items:
        img = it.get("image_filename") or ""
        it["image_url"] = f"/static/api_images/{img}"
        # Filter out rects for list view to keep small
        it.pop("rects", None)
    # Sort newest first
    items.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return items


@router.post("/apis")
async def create_api(request: Request, image: UploadFile = File(...), name: Optional[str] = None):
    _ensure_dirs()
    uid = _user_id(request)

    # Validate image type lightly
    content_type = (image.content_type or "").lower()
    if not (content_type.startswith("image/") or image.filename):
        raise HTTPException(status_code=400, detail="Image file required")

    api_id = uuid.uuid4().hex
    # Preserve extension if present
    ext = ""
    if image.filename and "." in image.filename:
        ext = "." + image.filename.rsplit(".", 1)[-1].lower()
        ext = ext[:16]
    filename = f"{api_id}{ext or '.png'}"
    out_path = IMAGES_DIR / filename

    # Save file
    with out_path.open("wb") as out:
        # Use shutil.copyfileobj for streamed write
        shutil.copyfileobj(image.file, out)

    now = _now_iso()
    doc: Dict[str, Any] = {
        "id": api_id,
        "user_id": uid,
        "name": (name or "Untitled API").strip() or "Untitled API",
        "created_at": now,
        "updated_at": now,
        "image_filename": filename,
        "rects": [],
    }
    _save_api(doc)

    doc["image_url"] = f"/static/api_images/{filename}"
    return doc


@router.get("/apis/{api_id}")
def get_api(api_id: str, request: Request):
    _ensure_dirs()
    uid = _user_id(request)
    doc = _load_api(api_id)
    if doc.get("user_id") != uid:
        raise HTTPException(status_code=403, detail="Forbidden")
    doc["image_url"] = f"/static/api_images/{doc.get('image_filename')}"
    return doc


class ApiUpdate(BaseModel):
    name: Optional[str] = None
    rects: Optional[List[Rect]] = None


@router.put("/apis/{api_id}")
def update_api(api_id: str, upd: ApiUpdate, request: Request):
    _ensure_dirs()
    uid = _user_id(request)
    doc = _load_api(api_id)
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

    doc["image_url"] = f"/static/api_images/{doc.get('image_filename')}"
    return doc


@router.delete("/apis/{api_id}")
def delete_api(api_id: str, request: Request):
    _ensure_dirs()
    uid = _user_id(request)
    doc = _load_api(api_id)
    if doc.get("user_id") != uid:
        raise HTTPException(status_code=403, detail="Forbidden")
    # Remove files
    p = _api_path(api_id)
    try:
        p.unlink(missing_ok=True)
    except Exception:
        pass
    img = doc.get("image_filename")
    if img:
        try:
            (IMAGES_DIR / img).unlink(missing_ok=True)
        except Exception:
            pass
    return {"ok": True}

