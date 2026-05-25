from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Set, Union

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi import Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

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
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str = ""
    x: float = Field(ge=0, le=1)
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(ge=1)
    h: int = Field(ge=1)
    theta: float = Field(default=0.0, alias="θ")
    # Horizontal separators inside the rectangle (pixels from top)
    seps: List[int] = Field(default_factory=list)
    manual: bool = False

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
    extract_text: List[Rect] = Field(default_factory=list)
    references: List[Rect] = Field(default_factory=list)
    noise: List[Rect] = Field(default_factory=list)


def _clean_rect(rect: Dict[str, Any]) -> Dict[str, Any]:
    data = dict(rect or {})
    rid = str(data.get("id") or "").strip()
    if not rid:
        rid = uuid.uuid4().hex
    data["id"] = rid
    data["name"] = str(data.get("name") or "")
    x_val = data.get("x", data.get("left", 0))
    y_val = data.get("y", data.get("top", 0))
    w_val = data.get("w", data.get("width", 1))
    h_val = data.get("h", data.get("height", 1))
    try:
        x_int = int(round(float(x_val)))
    except (TypeError, ValueError):
        x_int = 0
    try:
        y_int = int(round(float(y_val)))
    except (TypeError, ValueError):
        y_int = 0
    try:
        w_int = max(1, int(round(float(w_val))))
    except (TypeError, ValueError):
        w_int = 1
    try:
        h_int = max(1, int(round(float(h_val))))
    except (TypeError, ValueError):
        h_int = 1
    data["x"] = x_int
    data["y"] = y_int
    data["w"] = w_int
    data["h"] = h_int
    data["width"] = w_int
    data["height"] = h_int
    theta_val = data.get("θ", data.get("theta", 0))
    try:
        theta_num = float(theta_val)
    except (TypeError, ValueError):
        theta_num = 0.0
    if not theta_num == theta_num:  # NaN guard
        theta_num = 0.0
    data["θ"] = float(theta_num)
    data.pop("theta", None)
    seps = []
    for s in data.get("seps", []):
        try:
            seps.append(int(round(float(s))))
        except (TypeError, ValueError):
            continue
    data["seps"] = seps
    data.pop("extract_text", None)
    return data


def _sanitize_rect_input(
    raw: Union[Rect, Dict[str, Any], str, None],
    existing: Dict[str, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if raw is None:
        return None
    if isinstance(raw, Rect):
        data = raw.model_dump()
    elif isinstance(raw, dict):
        data = dict(raw)
    elif isinstance(raw, str):
        lookup = existing.get(raw)
        data = dict(lookup) if lookup else None
        if data is None:
            return None
    else:
        return None

    rid = str(data.get("id") or "").strip()
    if rid and rid in existing:
        base = dict(existing[rid])
        for key, value in data.items():
            if value is not None:
                base[key] = value
        data = base

    rect = _clean_rect(data)
    existing[rect["id"]] = rect
    return rect


def _normalize_doc_structure(doc: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(doc, dict):
        return doc

    raw_rects = doc.get("rects") if isinstance(doc.get("rects"), list) else []
    raw_extract = doc.get("extract_text") if isinstance(doc.get("extract_text"), list) else []
    raw_references = doc.get("references") if isinstance(doc.get("references"), list) else []
    raw_noise = doc.get("noise") if isinstance(doc.get("noise"), list) else []

    existing: Dict[str, Dict[str, Any]] = {}
    extract_target: List[Dict[str, Any]] = []
    reference_target: List[Dict[str, Any]] = []
    noise_target: List[Dict[str, Any]] = []
    extract_ids: Set[str] = set()
    reference_ids: Set[str] = set()
    noise_ids: Set[str] = set()

    for raw in raw_rects:
        rect = _sanitize_rect_input(raw, existing)
        if not rect:
            continue
        rid = rect["id"]
        if getattr(raw, "extract_text", None) is False or (isinstance(raw, dict) and raw.get("extract_text") is False):
            if rid not in noise_ids:
                noise_target.append(dict(rect))
                noise_ids.add(rid)
        else:
            if rid not in extract_ids:
                extract_target.append(dict(rect))
                extract_ids.add(rid)
    if "rects" in doc:
        doc.pop("rects", None)

    def _merge_group(raw_items: Iterable[Any], target: List[Dict[str, Any]], seen: Set[str]) -> None:
        for item in raw_items:
            rect = _sanitize_rect_input(item, existing)
            if not rect:
                continue
            rid = rect["id"]
            if rid in seen:
                continue
            seen.add(rid)
            target.append(dict(rect))

    _merge_group(raw_extract, extract_target, extract_ids)
    _merge_group(raw_references, reference_target, reference_ids)
    _merge_group(raw_noise, noise_target, noise_ids)

    doc["extract_text"] = extract_target
    doc["references"] = reference_target
    doc["noise"] = noise_target
    return doc


def _load_api(uid: str, api_id: str) -> Dict[str, Any]:
    found = find_doc_by_id(uid, api_id)
    if not found:
        raise HTTPException(status_code=404, detail="API not found")
    doc, _ = found
    return _normalize_doc_structure(doc)


def _save_api(doc: Dict[str, Any]) -> None:
    uid = doc["user_id"]
    name = doc["name"]
    blob_name = _doc_blob_by_name(uid, name)
    data = json.dumps(doc, ensure_ascii=False, indent=2).encode("utf-8")
    upload_bytes(data, blob_name, content_type="application/json")


def _list_user_apis(uid: str) -> List[Dict[str, Any]]:
    return [
        doc
        for doc in iter_user_docs(uid)
        if isinstance(doc, dict) and doc.get("kind") != "data_collector"
    ]


router = APIRouter(prefix="/builder", tags=["builder"])


@router.get("/health")
def health():
    return {"ok": True}


@router.get("/apis")
def list_apis(request: Request):
    uid = _user_id(request)
    items = _list_user_apis(uid)
    # Attach image_url and strip heavy fields for list view
    for idx, it in enumerate(items):
        it = _normalize_doc_structure(it)
        items[idx] = it
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
        "kind": "api_builder",
        "user_id": uid,
        "name": api_name,
        "created_at": now,
        "updated_at": now,
        "image_blob": img_blob,
        "extract_text": [],
        "references": [],
        "noise": [],
    }
    _save_api(doc)

    url = None
    try:
        url = signed_url(img_blob, minutes=20)
    except Exception:
        url = None

    resp = _normalize_doc_structure(dict(doc))
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
    resp = _normalize_doc_structure(dict(doc))
    resp["image_url"] = url or f"/builder/images/{api_id}"
    resp["access_url"] = _object_api_url(resp)
    return resp


class ApiUpdate(BaseModel):
    name: Optional[str] = None
    rects: Optional[List[Rect]] = None
    extract_text: Optional[List[Union[str, Rect, Dict[str, Any]]]] = None
    references: Optional[List[Union[str, Rect, Dict[str, Any]]]] = None
    noise: Optional[List[Union[str, Rect, Dict[str, Any]]]] = None


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
    doc = _normalize_doc_structure(doc)
    existing_lookup: Dict[str, Dict[str, Any]] = {}
    for group_name in ("extract_text", "references", "noise"):
        for entry in doc.get(group_name, []) or []:
            if isinstance(entry, dict) and entry.get("id"):
                existing_lookup[str(entry["id"])] = dict(entry)

    rect_payload_for_default: List[Dict[str, Any]] = []
    if upd.rects is not None:
        for raw in upd.rects:
            rect = _sanitize_rect_input(raw, existing_lookup)
            if rect:
                rect_payload_for_default.append(dict(rect))
        if rect_payload_for_default and upd.extract_text is None:
            doc["extract_text"] = rect_payload_for_default.copy()
            changed = True

    def apply_group(values: Optional[List[Union[str, Rect, Dict[str, Any]]]], key: str) -> None:
        nonlocal changed
        if values is None:
            return
        sanitized: List[Dict[str, Any]] = []
        seen: Set[str] = set()
        for item in values:
            rect = _sanitize_rect_input(item, existing_lookup)
            if not rect:
                continue
            rid = rect["id"]
            if rid in seen:
                continue
            seen.add(rid)
            sanitized.append(dict(rect))
        doc[key] = sanitized
        changed = True

    apply_group(upd.extract_text, "extract_text")
    apply_group(upd.references, "references")
    apply_group(upd.noise, "noise")

    doc = _normalize_doc_structure(doc)

    if changed:
        doc["updated_at"] = _now_iso()
        _save_api(doc)

    # Prefer a signed URL for faster reloads post-save
    url = None
    try:
        url = signed_url(doc.get("image_blob") or "", minutes=20)
    except Exception:
        url = None
    resp = _normalize_doc_structure(dict(doc))
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
