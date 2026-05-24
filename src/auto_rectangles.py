from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Iterable, List

import numpy as np
from PIL import Image, ImageFilter, ImageOps


@dataclass
class _Box:
    x: int
    y: int
    w: int
    h: int
    area: int


def _otsu_threshold(gray: np.ndarray) -> int:
    hist = np.bincount(gray.ravel(), minlength=256).astype(np.float64)
    total = float(gray.size)
    if total <= 0:
        return 127

    bins = np.arange(256, dtype=np.float64)
    weight_bg = np.cumsum(hist)
    weight_fg = total - weight_bg
    mean_bg = np.cumsum(hist * bins) / np.maximum(weight_bg, 1.0)
    mean_fg = (np.cumsum((hist * bins)[::-1]) / np.maximum(np.cumsum(hist[::-1]), 1.0))[::-1]
    between = weight_bg * weight_fg * np.square(mean_bg - mean_fg)
    return int(np.nanargmax(between))


def _filter_mask(mask: np.ndarray, *, max_size: int = 3, min_size: int = 3) -> np.ndarray:
    image = Image.fromarray((mask.astype(np.uint8) * 255), mode="L")
    if max_size > 1:
        image = image.filter(ImageFilter.MaxFilter(max_size))
    if min_size > 1:
        image = image.filter(ImageFilter.MinFilter(min_size))
    return np.asarray(image) > 0


def _prepare_mask(image: Image.Image) -> np.ndarray:
    gray = np.asarray(ImageOps.grayscale(image), dtype=np.uint8)
    threshold = min(238, _otsu_threshold(gray) + 8)
    dark = gray <= threshold

    gray_i = gray.astype(np.int16)
    gx = np.abs(gray_i[:, 1:] - gray_i[:, :-1])
    gy = np.abs(gray_i[1:, :] - gray_i[:-1, :])
    grad = np.zeros_like(gray_i, dtype=np.int16)
    grad[:, 1:] = np.maximum(grad[:, 1:], gx)
    grad[1:, :] = np.maximum(grad[1:, :], gy)
    edge_threshold = max(18, int(np.percentile(grad, 92)))
    edges = grad >= edge_threshold

    mask = np.logical_or(dark, edges)
    mask = _filter_mask(mask, max_size=5, min_size=3)
    mask = _filter_mask(mask, max_size=3, min_size=3)
    return mask


def _find(parent: List[int], value: int) -> int:
    root = value
    while parent[root] != root:
        root = parent[root]
    while parent[value] != value:
        nxt = parent[value]
        parent[value] = root
        value = nxt
    return root


def _union(parent: List[int], a: int, b: int) -> None:
    ra = _find(parent, a)
    rb = _find(parent, b)
    if ra == rb:
        return
    if ra < rb:
        parent[rb] = ra
    else:
        parent[ra] = rb


def _connected_boxes(mask: np.ndarray) -> List[_Box]:
    height, width = mask.shape
    labels = np.zeros((height, width), dtype=np.int32)
    parent: List[int] = [0]

    for y in range(height):
        xs = np.flatnonzero(mask[y])
        for x in xs:
            neighbors: List[int] = []
            if x > 0 and labels[y, x - 1]:
                neighbors.append(int(labels[y, x - 1]))
            if y > 0:
                x0 = max(0, x - 1)
                x1 = min(width, x + 2)
                row = labels[y - 1, x0:x1]
                neighbors.extend(int(v) for v in row if v)
            if not neighbors:
                parent.append(len(parent))
                labels[y, x] = len(parent) - 1
                continue
            label = min(neighbors)
            labels[y, x] = label
            for other in neighbors:
                _union(parent, label, other)

    stats: dict[int, list[int]] = {}
    ys, xs = np.nonzero(labels)
    for y, x in zip(ys.tolist(), xs.tolist()):
        label = _find(parent, int(labels[y, x]))
        if label not in stats:
            stats[label] = [x, y, x, y, 0]
        rec = stats[label]
        rec[0] = min(rec[0], x)
        rec[1] = min(rec[1], y)
        rec[2] = max(rec[2], x)
        rec[3] = max(rec[3], y)
        rec[4] += 1

    boxes = []
    for x0, y0, x1, y1, area in stats.values():
        boxes.append(_Box(x=x0, y=y0, w=x1 - x0 + 1, h=y1 - y0 + 1, area=area))
    return boxes


def _boxes_touch(a: _Box, b: _Box, gap: int) -> bool:
    return not (
        a.x + a.w + gap < b.x
        or b.x + b.w + gap < a.x
        or a.y + a.h + gap < b.y
        or b.y + b.h + gap < a.y
    )


def _merge_boxes(boxes: Iterable[_Box], *, gap: int) -> List[_Box]:
    merged: List[_Box] = []
    for box in sorted(boxes, key=lambda b: (b.y, b.x)):
        combined = box
        changed = True
        while changed:
            changed = False
            keep: List[_Box] = []
            for existing in merged:
                if _boxes_touch(combined, existing, gap):
                    x0 = min(combined.x, existing.x)
                    y0 = min(combined.y, existing.y)
                    x1 = max(combined.x + combined.w, existing.x + existing.w)
                    y1 = max(combined.y + combined.h, existing.y + existing.h)
                    combined = _Box(x0, y0, x1 - x0, y1 - y0, combined.area + existing.area)
                    changed = True
                else:
                    keep.append(existing)
            merged = keep
        merged.append(combined)
    return merged


def generate_rectangles_from_image_bytes(
    data: bytes,
    *,
    max_side: int = 1400,
    min_area_ratio: float = 0.000025,
    max_rectangles: int = 180,
) -> List[dict]:
    image = Image.open(BytesIO(data)).convert("RGB")
    orig_w, orig_h = image.size
    if orig_w <= 0 or orig_h <= 0:
        return []

    scale = 1.0
    longest = max(orig_w, orig_h)
    if longest > max_side:
        scale = max_side / float(longest)
        new_size = (max(1, int(round(orig_w * scale))), max(1, int(round(orig_h * scale))))
        image = image.resize(new_size, Image.Resampling.LANCZOS)

    det_w, det_h = image.size
    mask = _prepare_mask(image)
    raw_boxes = _connected_boxes(mask)

    min_area = max(24, int(det_w * det_h * min_area_ratio))
    min_w = max(4, int(round(det_w * 0.003)))
    min_h = max(4, int(round(det_h * 0.003)))
    max_area = det_w * det_h * 0.65
    filtered = [
        box
        for box in raw_boxes
        if box.area >= min_area
        and box.w >= min_w
        and box.h >= min_h
        and (box.w * box.h) <= max_area
    ]

    merged = _merge_boxes(filtered, gap=max(2, int(round(min(det_w, det_h) * 0.002))))
    merged = [
        box
        for box in merged
        if box.area >= min_area and box.w >= min_w and box.h >= min_h and (box.w * box.h) <= max_area
    ]
    if len(merged) > max_rectangles:
        merged = sorted(merged, key=lambda b: b.area, reverse=True)[:max_rectangles]
    merged.sort(key=lambda b: (b.y, b.x, -b.area))

    inv_scale_x = orig_w / float(det_w)
    inv_scale_y = orig_h / float(det_h)
    rects = []
    for idx, box in enumerate(merged, start=1):
        x = max(0, int(round(box.x * inv_scale_x)))
        y = max(0, int(round(box.y * inv_scale_y)))
        w = max(1, int(round(box.w * inv_scale_x)))
        h = max(1, int(round(box.h * inv_scale_y)))
        if x + w > orig_w:
            w = max(1, orig_w - x)
        if y + h > orig_h:
            h = max(1, orig_h - y)
        rects.append(
            {
                "id": f"auto-{idx:04d}",
                "name": f"field_{idx:03d}",
                "x": x,
                "y": y,
                "w": w,
                "h": h,
                "width": w,
                "height": h,
                "seps": [],
                "extract_text": True,
            }
        )
    return rects
