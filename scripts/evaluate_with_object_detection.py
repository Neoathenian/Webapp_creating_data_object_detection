from __future__ import annotations

import argparse
import base64
import contextlib
import copy
import json
import math
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
        "θ": float(rect.get("θ", rect.get("theta", 0.0)) or 0.0),
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


def _normalize_angle_deg(value: float) -> float:
    while value > 180.0:
        value -= 360.0
    while value <= -180.0:
        value += 360.0
    return value


def _resolve_global_theta_offset_deg(
    detection_result: dict,
    h_template_to_scene: np.ndarray,
    template_shape: tuple[int, int, int],
    cv2,
) -> float:
    raw = detection_result.get("angle_deg")
    try:
        reported_angle = float(raw)
    except (TypeError, ValueError):
        return 0.0
    if not reported_angle == reported_angle:
        return 0.0

    template_h, template_w = template_shape[:2]
    if template_w <= 0 or template_h <= 0:
        return 0.0

    top_edge = np.array([[[0.0, 0.0], [float(template_w - 1), 0.0]]], dtype=np.float32)
    top_edge_scene = cv2.perspectiveTransform(top_edge, h_template_to_scene)[0]
    edge = top_edge_scene[1] - top_edge_scene[0]
    mapped_angle = math.degrees(math.atan2(float(edge[1]), float(edge[0])))
    delta = _normalize_angle_deg(reported_angle - mapped_angle)

    # Keep only a meaningful correction: this catches the missed ±90° pass while
    # ignoring tiny numerical differences between estimators.
    if abs(delta) < 45.0:
        return 0.0
    return delta


def _map_rects_template_to_scene(
    rects: list[dict],
    h_template_to_scene: np.ndarray,
    cv2,
    scene_w: int,
    scene_h: int,
    theta_offset_deg: float = 0.0,
) -> list[dict]:
    def _theta_from_rect(rect: dict) -> float:
        raw = rect.get("θ", rect.get("theta", 0.0))
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = 0.0
        if not value == value:
            value = 0.0
        while value > 180.0:
            value -= 360.0
        while value <= -180.0:
            value += 360.0
        return value

    def _rotated_quad(x: float, y: float, w: float, h: float, theta_deg: float) -> np.ndarray:
        cx = x + (w / 2.0)
        cy = y + (h / 2.0)
        half_w = w / 2.0
        half_h = h / 2.0
        corners = np.array(
            [
                [-half_w, -half_h],
                [half_w, -half_h],
                [half_w, half_h],
                [-half_w, half_h],
            ],
            dtype=np.float64,
        )
        angle = math.radians(theta_deg)
        cos_v = math.cos(angle)
        sin_v = math.sin(angle)
        rot = np.array([[cos_v, -sin_v], [sin_v, cos_v]], dtype=np.float64)
        rotated = corners @ rot.T
        rotated[:, 0] += cx
        rotated[:, 1] += cy
        return rotated.astype(np.float32)

    mapped: list[dict] = []
    for rect in rects:
        x = float(rect.get("x", 0))
        y = float(rect.get("y", 0))
        w = float(rect.get("w", rect.get("width", 0)))
        h = float(rect.get("h", rect.get("height", 0)))
        theta = _theta_from_rect(rect)
        if w <= 0 or h <= 0:
            continue

        quad = np.array([_rotated_quad(x, y, w, h, theta)], dtype=np.float32)
        quad_scene = cv2.perspectiveTransform(quad, h_template_to_scene)[0]

        edge_x = quad_scene[1] - quad_scene[0]
        edge_y = quad_scene[3] - quad_scene[0]
        w_scene = float(np.linalg.norm(edge_x))
        h_scene = float(np.linalg.norm(edge_y))
        if w_scene <= 1e-6 or h_scene <= 1e-6:
            continue

        scene_theta = math.degrees(math.atan2(float(edge_x[1]), float(edge_x[0])))
        scene_theta = _normalize_angle_deg(scene_theta + theta_offset_deg)

        cx = float(np.mean(quad_scene[:, 0]))
        cy = float(np.mean(quad_scene[:, 1]))
        x_scene = cx - (w_scene / 2.0)
        y_scene = cy - (h_scene / 2.0)

        # Keep parameters in a sane numeric range for UI rendering.
        if x_scene > scene_w or y_scene > scene_h or (x_scene + w_scene) < 0 or (y_scene + h_scene) < 0:
            continue

        mapped.append(
            {
                "id": rect.get("id") or rect.get("name") or "",
                "name": rect.get("name") or "",
                "x": x_scene,
                "y": y_scene,
                "w": w_scene,
                "h": h_scene,
                "θ": scene_theta,
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
    theta_offset_deg = _resolve_global_theta_offset_deg(detection_result, h_template_to_scene, template_bgr.shape, cv2)

    def map_group(group: list[dict], flag: str) -> list[dict]:
        mapped = _map_rects_template_to_scene(
            group,
            h_template_to_scene,
            cv2,
            scene_bgr.shape[1],
            scene_bgr.shape[0],
            theta_offset_deg=theta_offset_deg,
        )
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
