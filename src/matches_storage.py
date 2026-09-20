"""Local OCR correspondence datasets; point ids are original detection indices."""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import tempfile
import threading
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

from src.gcs_storage import LOCAL_STORAGE_DIR

MATCHES_ROOT = LOCAL_STORAGE_DIR / "matches"
TEMPLATES_ROOT = LOCAL_STORAGE_DIR / "templates"
_SAVE_LOCK = threading.Lock()

_OCR_EQUIVALENCE_CANONICAL = {
    'o': '0',
    '0': '0',
    'i': '1',
    'l': '1',
    '1': '1',
}


class ConflictError(ValueError):
    pass


def canonical_label(label: str) -> str:
    value = str(label or '').strip()
    if len(value) != 1:
        return value
    return _OCR_EQUIVALENCE_CANONICAL.get(value.lower(), value)


def labels_match(left: str, right: str) -> bool:
    left_label = canonical_label(left)
    right_label = canonical_label(right)
    return bool(left_label) and left_label == right_label


def folder(template: str, sample: str | None = None) -> Path:
    parts = [template] if sample is None else [template, sample]
    for part in parts:
        if not part or part.startswith('.') or part.startswith('_') or any(c in part for c in '/\\'):
            raise ValueError("Invalid dataset name")
    path = MATCHES_ROOT.joinpath(*parts)
    if not path.resolve().is_relative_to(MATCHES_ROOT.resolve()):
        raise ValueError("Invalid dataset path")
    if not path.is_dir():
        raise FileNotFoundError("Dataset not found")
    return path


def ocr_data(path: Path) -> dict:
    data = json.loads((path / "ocr_character_overlay.json").read_text())
    if not isinstance(data, dict) or not isinstance(data.get('detections'), list):
        raise ValueError("OCR file must contain detections")
    return data


def coordinate_image(path: Path, data: dict, *, template: bool = False) -> bytes:
    if data.get('metadata', {}).get('coordinates') == 'rotated_image':
        # Use the embedded image, just as the API's cached OCR loader does.
        encoded = data.get('rotated_image_base64')
        if encoded:
            return base64.b64decode(encoded, validate=True)
        return (path / 'rotated_image.png').read_bytes()
    return (path / ('image.png' if template else 'input_image.png')).read_bytes()


def points(data: dict) -> list[dict]:
    result = []
    cluster_index = 0
    for index, detection in enumerate(data['detections']):
        label = str(detection.get('name') or detection.get('text') or '')
        poly = detection.get('poly')
        # Match Cluster_class.Cluster.mid_point: mean of polygon vertices.
        if poly and len(poly) == 4:
            x, y = map(float, np.asarray(poly, dtype=np.float32).mean(axis=0))
        else:
            x, y = map(float, detection['center'])
        if not math.isfinite(x) or not math.isfinite(y):
            raise ValueError('Non-finite OCR coordinates')
        result.append({'id': index, 'cluster_index': cluster_index if label else None,
                       'label': label, 'x': x, 'y': y})
        if label:
            cluster_index += 1
    return result


def template_keep_mask(doc: dict, width: int, height: int) -> np.ndarray:
    """Mirror the API's split_rects_by_seps + build_template_keep_mask.

    The API masks axis-aligned extraction/noise rectangles, including for
    boxes with theta. References do not restore pixels masked by another box.
    Keep its integer truncation and half-open pixel boundaries exactly.
    """
    mask = np.full((height, width), 255, dtype=np.uint8)
    for group in ('extract_text', 'noise'):
        rectangles = doc.get(group) or []
        if isinstance(rectangles, dict):
            rectangles = [rectangles]
        for rect in rectangles:
            x, y, w, h = (float(rect[key]) for key in ('x', 'y', 'w', 'h'))
            if not all(math.isfinite(value) for value in (x, y, w, h)):
                raise ValueError('Non-finite template bounding box')
            if w <= 0 or h <= 0:
                continue
            separators = []
            for value in rect.get('seps') or []:
                try:
                    separators.append(float(value))
                except (TypeError, ValueError):
                    continue
            if not all(0 <= value <= 1 for value in separators):
                separators = [value / h for value in separators]
            bounds = [0.0] + sorted(set(value for value in separators if 1e-9 < value < 1 - 1e-9)) + [1.0]
            for start, end in zip(bounds, bounds[1:]):
                x0, y0, rw, rh = int(x), int(y + start * h), int(w), int((end - start) * h)
                x1, y1 = min(width, x0 + rw), min(height, y0 + rh)
                x0, y0 = max(0, x0), max(0, y0)
                if x1 > x0 and y1 > y0:
                    mask[y0:y1, x0:x1] = 0
    return mask


def filter_template_points(pts: list[dict], mask: np.ndarray) -> list[dict]:
    height, width = mask.shape
    result = []
    matching_index = 0
    for point in pts:
        # Cluster.is_in_mask rounds its float32 polygon centroid with np.round.
        x, y = np.round([point['x'], point['y']]).astype(int)
        if 0 <= x < width and 0 <= y < height and mask[y, x]:
            kept = dict(point, matching_cluster_index=matching_index if point['label'] else None)
            result.append(kept)
            if point['label']:
                matching_index += 1
    return result


def side_data(path: Path, *, template: bool = False) -> dict:
    data = ocr_data(path)
    image = coordinate_image(path, data, template=template)
    with Image.open(BytesIO(image)) as opened:
        width, height = opened.size
    pts = points(data)
    coordinates = data.get('metadata', {}).get('coordinates', 'source_image')
    fingerprint_input = json.dumps([data['detections'], coordinates], sort_keys=True).encode() + image
    excluded_count = 0
    if template:
        doc = json.loads((path / 'bboxes.json').read_text())
        mask = template_keep_mask(doc, width, height)
        kept = filter_template_points(pts, mask)
        excluded_count = len(pts) - len(kept)
        pts = kept
        fingerprint_input += mask.tobytes()
    fingerprint = hashlib.sha256(fingerprint_input).hexdigest()
    return {'points': pts, 'width': width, 'height': height,
            'coordinate_space': coordinates, 'fingerprint': fingerprint,
            'excluded_point_count': excluded_count}


def template_folder(template: str) -> Path:
    folder(template)  # Validate the name and its dataset directory.
    path = TEMPLATES_ROOT / template
    if not path.resolve().is_relative_to(TEMPLATES_ROOT.resolve()):
        raise ValueError('Invalid template path')
    return path


def read_annotations(path: Path) -> dict:
    file = path / 'manual_matches.json'
    return json.loads(file.read_text()) if file.exists() else {'revision': 0, 'pairs': []}


def load_pair(template: str, sample: str) -> dict:
    path = folder(template, sample)
    left = side_data(template_folder(template), template=True)
    right = side_data(path)
    saved = read_annotations(path)
    fingerprints = {'template': left['fingerprint'], 'scene': right['fingerprint']}
    if saved.get('fingerprints', fingerprints) != fingerprints:
        raise ConflictError('Template OCR, image, or bounding-box mask changed since annotation, or scene OCR changed. Saved matches must be reviewed against their original inputs before editing.')
    return {'template_name': template, 'sample_name': sample, 'template': left, 'scene': right,
            'pairs': saved['pairs'], 'revision': saved['revision'], 'fingerprints': fingerprints}


def save_pair(template: str, sample: str, pairs: list[dict], revision: int, fingerprints: dict) -> dict:
    with _SAVE_LOCK:
        data = load_pair(template, sample)
        if revision != data['revision'] or fingerprints != data['fingerprints']:
            raise ConflictError('This sample changed. Reload it before saving to avoid overwriting newer work.')
        left = {p['id']: p for p in data['template']['points']}
        right = {p['id']: p for p in data['scene']['points']}
        used_left, used_right = set(), set()
        for pair in pairs:
            t, s = pair['template_id'], pair['scene_id']
            if t not in left or s not in right:
                raise ValueError('Unknown OCR point')
            if not labels_match(left[t]['label'], right[s]['label']):
                raise ValueError('Matches must have the same nonempty OCR character')
            if t in used_left or s in used_right:
                raise ValueError('Each point can only belong to one match')
            used_left.add(t)
            used_right.add(s)
        doc = {'schema_version': 1, 'template_name': template, 'sample_name': sample,
               'matching_rule': 'exact_character_one_to_one', 'fingerprints': fingerprints,
               'revision': revision + 1, 'updated_at': datetime.now(timezone.utc).isoformat(),
               'coordinate_spaces': {side: data[side]['coordinate_space'] for side in ('template', 'scene')},
               'pairs': pairs}
        path = folder(template, sample) / 'manual_matches.json'
        fd, temporary = tempfile.mkstemp(prefix='.matches-', suffix='.tmp', dir=path.parent)
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(doc, stream, indent=2, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return doc


def catalog() -> list[dict]:
    result = []
    if not MATCHES_ROOT.exists():
        return result
    for path in sorted(MATCHES_ROOT.iterdir()):
        if not path.is_dir() or path.name.startswith(('.', '_')):
            continue
        samples = []
        for sample in sorted(path.iterdir()):
            if sample.is_dir() and (sample / 'ocr_character_overlay.json').is_file():
                saved = read_annotations(sample)
                samples.append({'name': sample.name, 'matches': len(saved['pairs']), 'reviewed': saved['revision'] > 0})
        result.append({'name': path.name, 'samples': samples,
                       'error_count': len(list(path.glob('*.error.json')))})
    return result
