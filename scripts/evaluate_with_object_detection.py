from __future__ import annotations

import argparse
import base64
import contextlib
import copy
import json
import sys
from pathlib import Path

import numpy as np


def _rect_groups(doc: dict) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    extract_text = [copy.deepcopy(r) for r in doc.get("extract_text") or [] if isinstance(r, dict)]
    references = [copy.deepcopy(r) for r in doc.get("references") or [] if isinstance(r, dict)]
    noise = [copy.deepcopy(r) for r in doc.get("noise") or [] if isinstance(r, dict)]
    legacy = [copy.deepcopy(r) for r in doc.get("rects") or [] if isinstance(r, dict)]

    union: dict[str, dict] = {}
    for group in (legacy, extract_text, references, noise):
        for rect in group:
            rid = str(rect.get("id") or f"rect-{len(union)}")
            union[rid] = copy.deepcopy(rect)
    rects = list(union.values())
    if not extract_text and legacy:
        extract_text = [copy.deepcopy(r) for r in legacy if r.get("extract_text", True)]
        noise.extend(copy.deepcopy(r) for r in legacy if not r.get("extract_text", True))
    return rects, extract_text, references, noise


def _encode_png_b64(cv2, image) -> str:
    ok, buffer = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError("Failed to encode evaluated image.")
    return base64.b64encode(buffer).decode("ascii")


def _safe_rect_payload(rect: dict) -> dict:
    return {
        "id": rect.get("id") or rect.get("name") or "",
        "name": rect.get("name") or "",
        "x": int(round(float(rect.get("x", 0)))),
        "y": int(round(float(rect.get("y", 0)))),
        "w": max(1, int(round(float(rect.get("w", rect.get("width", 1)))))),
        "h": max(1, int(round(float(rect.get("h", rect.get("height", 1)))))),
        "width": max(1, int(round(float(rect.get("w", rect.get("width", 1)))))),
        "height": max(1, int(round(float(rect.get("h", rect.get("height", 1)))))),
        "seps": [int(round(float(v))) for v in rect.get("seps", []) if str(v).strip()],
    }


def _template_to_scene_homography(result: dict, scene_shape: tuple[int, int, int], scene_min_side: int) -> np.ndarray:
    scene_h, scene_w = scene_shape[:2]
    alpha = float(scene_min_side) / float(min(scene_h, scene_w))
    if alpha <= 0:
        raise RuntimeError("Invalid scene scale during evaluation mapping.")
    scale_back = np.array(
        [[1.0 / alpha, 0.0, 0.0], [0.0, 1.0 / alpha, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    h_template_to_det = np.asarray(result["homography"], dtype=np.float64)
    return scale_back @ h_template_to_det


def _map_rects_template_to_scene(rects: list[dict], h_template_to_scene: np.ndarray, cv2, scene_w: int, scene_h: int) -> list[dict]:
    mapped: list[dict] = []
    for rect in rects:
        x = float(rect.get("x", 0))
        y = float(rect.get("y", 0))
        w = float(rect.get("w", rect.get("width", 0)))
        h = float(rect.get("h", rect.get("height", 0)))
        if w <= 0 or h <= 0:
            continue

        quad = np.array([[[x, y], [x + w, y], [x + w, y + h], [x, y + h]]], dtype=np.float32)
        quad_scene = cv2.perspectiveTransform(quad, h_template_to_scene)[0]

        min_x = float(np.clip(np.min(quad_scene[:, 0]), 0, max(scene_w - 1, 0)))
        max_x = float(np.clip(np.max(quad_scene[:, 0]), 0, max(scene_w - 1, 0)))
        min_y = float(np.clip(np.min(quad_scene[:, 1]), 0, max(scene_h - 1, 0)))
        max_y = float(np.clip(np.max(quad_scene[:, 1]), 0, max(scene_h - 1, 0)))

        if max_x <= min_x or max_y <= min_y:
            continue

        mapped.append(
            {
                "id": rect.get("id") or rect.get("name") or "",
                "name": rect.get("name") or "",
                "x": min_x,
                "y": min_y,
                "w": max_x - min_x,
                "h": max_y - min_y,
            }
        )
    return mapped


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--object-root", required=True)
    parser.add_argument("--template-doc", required=True)
    parser.add_argument("--template-image", required=True)
    parser.add_argument("--scene-image", required=True)
    parser.add_argument("--template-min-side", type=int, default=500)
    parser.add_argument("--scene-scales", default="900,700,500")
    args = parser.parse_args()

    object_root = Path(args.object_root).resolve()
    sys.path.insert(0, str(object_root))

    import cv2  # type: ignore
    from src.template_image_class import TemplateImage  # type: ignore
    from src.detect_image import detect_image  # type: ignore

    doc = json.loads(Path(args.template_doc).read_text(encoding="utf-8"))
    template_bgr = cv2.imread(str(args.template_image), cv2.IMREAD_COLOR)
    scene_bgr = cv2.imread(str(args.scene_image), cv2.IMREAD_COLOR)
    if template_bgr is None:
        raise RuntimeError("Template image could not be read.")
    if scene_bgr is None:
        raise RuntimeError("Scene image could not be read.")

    rects, extract_text, references, noise = _rect_groups(doc)
    if not rects:
        raise RuntimeError("Template has no rectangles.")

    template = TemplateImage(
        template_bgr,
        rects,
        extract_text=extract_text,
        references=references,
        noise=noise,
        size_min_side=args.template_min_side,
    )
    scene_scales = tuple(int(v) for v in args.scene_scales.split(",") if v.strip())
    with contextlib.redirect_stdout(sys.stderr):
        detection_result, meta = detect_image(scene_bgr, template, scene_scales=scene_scales, min_inliers=8)
    if detection_result is None:
        print(json.dumps({"success": False, "confidence_score": 0.0, "message": "Template detection failed."}))
        return 0

    score = round(float(detection_result.get("return_pct_x_success", 0.0)), 3)
    h_template_to_scene = _template_to_scene_homography(detection_result, scene_bgr.shape, scene_scales[0])

    def map_group(group: list[dict], flag: str) -> list[dict]:
        mapped = _map_rects_template_to_scene(group, h_template_to_scene, cv2, scene_bgr.shape[1], scene_bgr.shape[0])
        out = []
        for item in mapped:
            payload = _safe_rect_payload(item)
            payload[flag] = True
            out.append(payload)
        return out

    payload = {
        "success": score >= 0.2,
        "confidence_score": score,
        "evaluated_image_base64": _encode_png_b64(cv2, scene_bgr),
        "image_width": int(scene_bgr.shape[1]),
        "image_height": int(scene_bgr.shape[0]),
        "extract_text": map_group(template.extract_text, "extract_text"),
        "references": map_group(template.references, "reference"),
        "noise": map_group(template.noise, "noise"),
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
