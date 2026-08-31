from __future__ import annotations

import json
import base64
import hashlib
import math
import os
import re
import subprocess
import tempfile
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi import Request
from fastapi.responses import Response
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel

from src.api_builder_router import (
    ApiUpdate,
    Rect,
    _clean_rotation,
    _image_blob_by_name,
    _now_iso,
    _normalize_doc_structure,
    _sanitize_rect_input,
    _user_id,
)
from src.gcs_storage import (
    delete_prefix,
    download_bytes,
    iter_user_docs,
    signed_url,
    upload_bytes,
)


COLLECTOR_KIND = "data_collector"
COLLECTOR_ROOT = "data_collector"
_UNSAFE_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

router = APIRouter(prefix="/data-collector", tags=["data-collector"])


def _doc_blob_by_name(uid: str, item_name: str) -> str:
    return f"{uid}/{COLLECTOR_ROOT}/{item_name}/bboxes.json"


def _collector_image_blob_by_name(uid: str, item_name: str, ext: str) -> str:
    return _image_blob_by_name(uid, f"{COLLECTOR_ROOT}/{item_name}", ext)


def _is_collector_doc(doc: Dict[str, Any]) -> bool:
    return doc.get("kind") == COLLECTOR_KIND


def _list_items(uid: str) -> List[Dict[str, Any]]:
    return [doc for doc in iter_user_docs(uid) if isinstance(doc, dict) and _is_collector_doc(doc)]


def _list_templates(uid: str) -> List[Dict[str, Any]]:
    return [
        doc
        for doc in iter_user_docs(uid)
        if isinstance(doc, dict) and doc.get("kind") != COLLECTOR_KIND
    ]


def _find_template(uid: str, template_id: str) -> Optional[Dict[str, Any]]:
    for doc in _list_templates(uid):
        if str(doc.get("id")) == str(template_id):
            return _normalize_doc_structure(doc)
    return None


def _find_item(uid: str, item_id: str) -> Optional[Dict[str, Any]]:
    for doc in _list_items(uid):
        if str(doc.get("id")) == str(item_id):
            return doc
    return None


def _load_item(uid: str, item_id: str) -> Dict[str, Any]:
    doc = _find_item(uid, item_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Data item not found")
    return _normalize_doc_structure(doc)


def _save_item(doc: Dict[str, Any]) -> None:
    uid = doc["user_id"]
    name = doc.get("storage_name") or doc["name"]
    blob_name = _doc_blob_by_name(uid, name)
    data = json.dumps(doc, ensure_ascii=False, indent=2).encode("utf-8")
    upload_bytes(data, blob_name, content_type="application/json")


def _response_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    resp = _normalize_doc_structure(dict(doc))
    raw_blob = resp.get("image_blob") or ""
    evaluated_blob = resp.get("evaluated_image_blob") or ""
    url = None
    try:
        url = signed_url(raw_blob, minutes=20)
    except Exception:
        url = None
    cache_key = resp.get("updated_at") or resp.get("id") or ""
    resp["image_url"] = url or f"/data-collector/images/{resp.get('id')}?view=raw&v={cache_key}"
    if evaluated_blob:
        evaluated_url = None
        try:
            evaluated_url = signed_url(evaluated_blob, minutes=20)
        except Exception:
            evaluated_url = None
        resp["evaluated_image_url"] = evaluated_url or f"/data-collector/images/{resp.get('id')}?view=evaluated&v={cache_key}"
    return resp


def _response_template(doc: Dict[str, Any]) -> Dict[str, Any]:
    resp = _normalize_doc_structure(dict(doc))
    url = None
    try:
        url = signed_url(resp.get("image_blob") or "", minutes=20)
    except Exception:
        url = None
    resp["image_url"] = url or f"/builder/images/{resp.get('id')}"
    return resp


def _item_matches_template(doc: Dict[str, Any], template_id: Optional[str]) -> bool:
    if not template_id:
        return True
    return str(doc.get("template_id") or "") == str(template_id)


def _item_blob_name(template_name: str, digest: str) -> str:
    safe_template = (template_name or "template").strip().replace("/", "-") or "template"
    return f"{safe_template}/{digest[:16]}"


def _find_duplicate(uid: str, template_id: str, digest: str) -> Optional[Dict[str, Any]]:
    for doc in _list_items(uid):
        if str(doc.get("template_id") or "") == str(template_id) and doc.get("sha256") == digest:
            return doc
    return None


def _crop_output_root() -> Path:
    configured = os.getenv("CROP_OUTPUT_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[1] / "crops"


def _safe_path_part(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    text = _UNSAFE_PATH_CHARS.sub("-", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text[:120] or fallback


def _item_output_folder_name(doc: Dict[str, Any]) -> str:
    raw = doc.get("original_filename") or doc.get("name") or doc.get("storage_name") or doc.get("id")
    base = Path(str(raw or "").replace("\\", "/")).name
    stem = Path(base).stem or base
    fallback = str(doc.get("id") or "image")[:12] or "image"
    return _safe_path_part(stem, fallback)


def _rect_name(rect: Dict[str, Any], index: int) -> str:
    return _safe_path_part(rect.get("name"), f"crop-{index + 1}")


def _named_crop_rects(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    normalized = _normalize_doc_structure(dict(doc))
    rects: List[Dict[str, Any]] = []
    seen_ids: Set[str] = set()
    for group_name in ("extract_text", "references", "noise"):
        for rect in normalized.get(group_name, []) or []:
            if not isinstance(rect, dict):
                continue
            if not str(rect.get("name") or "").strip():
                continue
            rid = str(rect.get("id") or "")
            if rid and rid in seen_ids:
                continue
            if rid:
                seen_ids.add(rid)
            rects.append(rect)
    return rects


def _rect_float(rect: Dict[str, Any], key: str, fallback: float = 0.0) -> float:
    try:
        value = rect.get(key, rect.get({"x": "left", "y": "top", "w": "width", "h": "height"}.get(key, key), fallback))
        num = float(value)
    except (TypeError, ValueError):
        return fallback
    return num if math.isfinite(num) else fallback


def _crop_rect(image: Image.Image, rect: Dict[str, Any]) -> Image.Image:
    x = int(round(_rect_float(rect, "x")))
    y = int(round(_rect_float(rect, "y")))
    w = max(1, int(round(_rect_float(rect, "w", 1.0))))
    h = max(1, int(round(_rect_float(rect, "h", 1.0))))
    theta = _rect_float(rect, "θ", _rect_float(rect, "theta", 0.0))

    source = image.convert("RGB")
    angle = math.radians(theta)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    cx = x + (w / 2.0)
    cy = y + (h / 2.0)
    coeffs = (
        cos_a,
        -sin_a,
        cx - (cos_a * w / 2.0) + (sin_a * h / 2.0),
        sin_a,
        cos_a,
        cy - (sin_a * w / 2.0) - (cos_a * h / 2.0),
    )
    return source.transform(
        (w, h),
        Image.Transform.AFFINE,
        coeffs,
        resample=Image.Resampling.BICUBIC,
        fillcolor=(255, 255, 255),
    )


def _load_image_from_blob(blob_name: str) -> Image.Image:
    try:
        data = download_bytes(blob_name)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Image not found") from exc
    try:
        with Image.open(BytesIO(data)) as img:
            return ImageOps.exif_transpose(img).copy()
    except UnidentifiedImageError as exc:
        raise HTTPException(status_code=422, detail="Stored image could not be opened") from exc


def _crop_template_item_bboxes(uid: str, template_id: str) -> Dict[str, Any]:
    template = _find_template(uid, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    template_name = str(template.get("name") or template_id or "template")
    template_dir = _crop_output_root() / _safe_path_part(template_name, "template")
    items = [_normalize_doc_structure(doc) for doc in _list_items(uid) if _item_matches_template(doc, template_id)]

    folder_counts: Dict[str, int] = {}
    processed_items = 0
    crop_count = 0
    skipped_items = 0
    errors: List[Dict[str, Any]] = []

    for doc in items:
        rects = _named_crop_rects(doc)
        if not rects:
            skipped_items += 1
            continue

        folder_base = _item_output_folder_name(doc)
        folder_count = folder_counts.get(folder_base, 0) + 1
        folder_counts[folder_base] = folder_count
        if folder_count == 1:
            folder_name = folder_base
        else:
            suffix = str(doc.get("sha256") or doc.get("id") or folder_count)[:8] or str(folder_count)
            folder_name = _safe_path_part(f"{folder_base}-{suffix}", f"image-{folder_count}")
        item_dir = template_dir / folder_name

        try:
            image = _load_image_from_blob(doc.get("image_blob") or "")
        except HTTPException as exc:
            errors.append({"item": doc.get("name") or doc.get("id"), "error": str(exc.detail)})
            continue

        item_dir.mkdir(parents=True, exist_ok=True)
        name_counts: Dict[str, int] = {}
        item_crops = 0
        for index, rect in enumerate(rects):
            output_base = _rect_name(rect, index)
            name_count = name_counts.get(output_base, 0) + 1
            name_counts[output_base] = name_count
            filename = f"{output_base}.png" if name_count == 1 else f"{output_base}-{name_count}.png"
            try:
                crop = _crop_rect(image, rect)
                crop.save(item_dir / filename, format="PNG")
                crop_count += 1
                item_crops += 1
            except Exception as exc:
                errors.append({
                    "item": doc.get("name") or doc.get("id"),
                    "rect": rect.get("name") or rect.get("id"),
                    "error": str(exc),
                })
        if item_crops:
            processed_items += 1
        else:
            skipped_items += 1

    return {
        "ok": True,
        "template_id": template.get("id"),
        "template_name": template_name,
        "output_dir": str(template_dir),
        "items": len(items),
        "processed_items": processed_items,
        "skipped_items": skipped_items,
        "crops": crop_count,
        "errors": errors[:50],
        "error_count": len(errors),
    }


def _object_detection_root() -> Path:
    configured = os.getenv("OBJECT_DETECTION_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path(__file__).resolve().parents[2] / "API_Object_detection").resolve()


def _object_detection_python(root: Path) -> Path:
    configured = os.getenv("OBJECT_DETECTION_PYTHON", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return root / "PythonPortable" / "env" / "bin" / "python"


def _blob_to_temp_file(blob_name: str, suffix: str, directory: Path) -> Path:
    path = directory / f"{uuid.uuid4().hex}{suffix}"
    path.write_bytes(download_bytes(blob_name))
    return path


def _run_evaluation(template_doc: Dict[str, Any], item_doc: Dict[str, Any]) -> Dict[str, Any]:
    root = _object_detection_root()
    python_bin = _object_detection_python(root)
    script = Path(__file__).resolve().parents[1] / "scripts" / "evaluate_with_object_detection.py"
    if not root.exists():
        raise HTTPException(status_code=500, detail=f"Object detection root not found: {root}")
    if not python_bin.exists():
        raise HTTPException(status_code=500, detail=f"Object detection Python not found: {python_bin}")
    if not script.exists():
        raise HTTPException(status_code=500, detail="Evaluation helper script is missing")

    with tempfile.TemporaryDirectory(prefix="collector-eval-") as td:
        temp_dir = Path(td)
        template_doc_path = temp_dir / "template_bboxes.json"
        template_doc_path.write_text(json.dumps(template_doc, ensure_ascii=False), encoding="utf-8")
        template_image = _blob_to_temp_file(template_doc.get("image_blob") or "", ".template.png", temp_dir)
        scene_image = _blob_to_temp_file(item_doc.get("image_blob") or "", ".scene.png", temp_dir)
        proc = subprocess.run(
            [
                str(python_bin),
                str(script),
                "--object-root",
                str(root),
                "--template-doc",
                str(template_doc_path),
                "--template-image",
                str(template_image),
                "--scene-image",
                str(scene_image),
            ],
            cwd=str(root),
            text=True,
            capture_output=True,
            timeout=int(os.getenv("DATA_COLLECTOR_EVAL_TIMEOUT", "120")),
        )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "Evaluation failed").strip()[-2000:]
        raise HTTPException(status_code=500, detail=detail)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Evaluation returned invalid JSON: {proc.stdout[-1000:]}") from exc


@router.get("/health")
def health():
    return {"ok": True}


@router.get("/templates")
def list_templates(request: Request):
    uid = _user_id(request)
    items = [_response_template(doc) for doc in _list_templates(uid)]
    items.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return items


@router.post("/templates/{template_id}/crop-bboxes")
def crop_template_bboxes(template_id: str, request: Request):
    uid = _user_id(request)
    return _crop_template_item_bboxes(uid, template_id)


@router.get("/apis")
def list_items(request: Request, template_id: Optional[str] = None):
    uid = _user_id(request)
    items = [_response_doc(doc) for doc in _list_items(uid) if _item_matches_template(doc, template_id)]
    items.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return items


@router.post("/apis")
async def create_item(
    request: Request,
    template_id: str,
    image: Optional[UploadFile] = File(default=None),
    images: Optional[List[UploadFile]] = File(default=None),
):
    uid = _user_id(request)
    template = _find_template(uid, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    uploads = list(images or [])
    if image is not None:
        uploads.append(image)
    uploads = [upload for upload in uploads if upload is not None]
    if not uploads:
        raise HTTPException(status_code=400, detail="Image file required")

    created: List[Dict[str, Any]] = []
    duplicates: List[Dict[str, Any]] = []
    for upload in uploads:
        content_type = (upload.content_type or "").lower()
        if not (content_type.startswith("image/") or upload.filename):
            continue
        data = await upload.read()
        if not data:
            continue
        digest = hashlib.sha256(data).hexdigest()
        duplicate = _find_duplicate(uid, template_id, digest)
        if duplicate:
            dup_resp = _response_doc(duplicate)
            dup_resp["duplicate"] = True
            dup_resp["original_filename"] = upload.filename or dup_resp.get("original_filename") or ""
            duplicates.append(dup_resp)
            continue

        item_id = uuid.uuid4().hex
        item_name = _item_blob_name(template.get("name") or template_id, digest)
        ext = ""
        if upload.filename and "." in upload.filename:
            ext = upload.filename.rsplit(".", 1)[-1]
        img_blob = _collector_image_blob_by_name(uid, item_name, ext)
        upload_bytes(data, img_blob, content_type=content_type or None)

        now = _now_iso()
        doc: Dict[str, Any] = {
            "id": item_id,
            "kind": COLLECTOR_KIND,
            "user_id": uid,
            "template_id": template.get("id"),
            "template_name": template.get("name"),
            "name": upload.filename or item_name.rsplit("/", 1)[-1],
            "storage_name": item_name,
            "sha256": digest,
            "original_filename": upload.filename or "",
            "created_at": now,
            "updated_at": now,
            "image_blob": img_blob,
            "rotation": 0,
            "extract_text": [],
            "references": [],
            "noise": [],
        }
        _save_item(doc)
        created.append(_response_doc(doc))

    items = created + duplicates
    if len(items) == 1:
        return items[0]
    return {"created": created, "duplicates": duplicates, "items": items}


@router.get("/apis/{item_id}")
def get_item(item_id: str, request: Request):
    uid = _user_id(request)
    doc = _load_item(uid, item_id)
    if doc.get("user_id") != uid:
        raise HTTPException(status_code=403, detail="Forbidden")
    return _response_doc(doc)


@router.put("/apis/{item_id}")
def update_item(item_id: str, upd: ApiUpdate, request: Request):
    uid = _user_id(request)
    doc = _load_item(uid, item_id)
    if doc.get("user_id") != uid:
        raise HTTPException(status_code=403, detail="Forbidden")

    changed = False
    storage_name = doc.get("storage_name") or doc.get("name") or ""
    if upd.name is not None:
        new_name = (upd.name or "").strip() or doc.get("name") or ""
        if new_name != doc.get("name"):
            doc["name"] = new_name
            doc["updated_at"] = _now_iso()
            changed = True
    if upd.rotation is not None:
        rotation = _clean_rotation(upd.rotation)
        if rotation != _clean_rotation(doc.get("rotation", 0)):
            doc["rotation"] = rotation
            changed = True

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
    doc["kind"] = COLLECTOR_KIND

    if changed:
        doc["updated_at"] = _now_iso()
        _save_item(doc)

    return _response_doc(doc)


class GeneratedRectangles(BaseModel):
    rectangles: List[Dict[str, Any]]
    count: int


@router.post("/apis/{item_id}/evaluate")
def evaluate_item(item_id: str, request: Request):
    uid = _user_id(request)
    doc = _load_item(uid, item_id)
    if doc.get("user_id") != uid:
        raise HTTPException(status_code=403, detail="Forbidden")

    template_id = str(doc.get("template_id") or "")
    template = _find_template(uid, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    result = _run_evaluation(template, doc)
    if result.get("evaluated_image_base64"):
        try:
            evaluated_bytes = base64.b64decode(result["evaluated_image_base64"])
        except Exception:
            evaluated_bytes = b""
        if evaluated_bytes:
            storage_name = doc.get("storage_name") or _item_blob_name(doc.get("template_name") or "template", doc.get("sha256") or uuid.uuid4().hex)
            evaluated_blob = f"{uid}/{COLLECTOR_ROOT}/{storage_name}/evaluated.png"
            upload_bytes(evaluated_bytes, evaluated_blob, content_type="image/png")
            doc["evaluated_image_blob"] = evaluated_blob

    if result.get("evaluated_image_base64"):
        doc["extract_text"] = result.get("extract_text") or []
        doc["references"] = result.get("references") or []
        doc["noise"] = result.get("noise") or []
    doc["evaluation"] = {
        "success": bool(result.get("success")),
        "confidence_score": float(result.get("confidence_score") or 0),
        "message": result.get("message") or "",
        "image_width": result.get("image_width"),
        "image_height": result.get("image_height"),
        "evaluated_at": _now_iso(),
    }
    doc["updated_at"] = _now_iso()
    doc["kind"] = COLLECTOR_KIND
    _save_item(doc)
    return _response_doc(doc)


@router.post("/apis/{item_id}/generate-rectangles", response_model=GeneratedRectangles)
def generate_rectangles(item_id: str, request: Request):
    from src.auto_rectangles import generate_rectangles_from_image_bytes

    uid = _user_id(request)
    doc = _load_item(uid, item_id)
    if doc.get("user_id") != uid:
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        data = download_bytes(doc.get("image_blob") or "")
    except Exception:
        raise HTTPException(status_code=404, detail="Image not found")

    try:
        rectangles = generate_rectangles_from_image_bytes(data)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to generate rectangles: {exc}")

    rectangles = [
        {**(_normalize_doc_structure({"extract_text": [rect]}).get("extract_text", [rect])[0]), "extract_text": True}
        for rect in rectangles
    ]
    return {"rectangles": rectangles, "count": len(rectangles)}


@router.delete("/apis/{item_id}")
def delete_item(item_id: str, request: Request):
    uid = _user_id(request)
    doc = _load_item(uid, item_id)
    if doc.get("user_id") != uid:
        raise HTTPException(status_code=403, detail="Forbidden")
    storage_name = doc.get("storage_name") or doc.get("name")
    delete_prefix(f"{uid}/{COLLECTOR_ROOT}/{storage_name}/")
    return {"ok": True}


@router.get("/images/{item_id}")
def fetch_image(item_id: str, request: Request, view: str = "raw"):
    uid = _user_id(request)
    doc = _load_item(uid, item_id)
    if doc.get("user_id") != uid:
        raise HTTPException(status_code=403, detail="Forbidden")
    img_blob = doc.get("image_blob") or ""
    if view == "evaluated" and doc.get("evaluated_image_blob"):
        img_blob = doc.get("evaluated_image_blob") or img_blob
    try:
        data = download_bytes(img_blob)
    except Exception:
        raise HTTPException(status_code=404, detail="Image not found")
    ctype = "image/png"
    if ".jpg" in img_blob or ".jpeg" in img_blob:
        ctype = "image/jpeg"
    elif ".webp" in img_blob:
        ctype = "image/webp"
    elif ".gif" in img_blob:
        ctype = "image/gif"
    resp = Response(content=data, media_type=ctype)
    resp.headers["Cache-Control"] = "private, max-age=60"
    return resp
