"""Suggestions from the API matching stage, kept separate from manual matches."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from src import matches_storage as store

_RUN_LOCK = threading.Lock()


class PredictionError(RuntimeError):
    pass


def algorithm_root() -> Path:
    configured = os.getenv('OBJECT_DETECTION_ROOT', '').strip()
    return Path(configured).expanduser().resolve() if configured else Path(__file__).resolve().parents[2] / 'API/API_Object_detection'


def algorithm_version(root: Path) -> str:
    algorithm = root / 'Object_detection_algorithm'
    digest = hashlib.sha256()
    for path in [algorithm / 'run_pipeline.py', *sorted((algorithm / 'src').rglob('*.py'))]:
        if not path.is_file():
            raise PredictionError('Object detection algorithm not found. Check OBJECT_DETECTION_ROOT.')
        digest.update(path.relative_to(algorithm).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def cached(template: str, sample: str, data: dict) -> dict | None:
    path = store.folder(template, sample) / 'predicted_matches.json'
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
        if payload['fingerprints'] == data['fingerprints'] and payload['algorithm_version'] == algorithm_version(algorithm_root()):
            return payload
    except (ValueError, KeyError, OSError, PredictionError):
        pass
    return None


def map_predictions(records: list[dict], data: dict) -> tuple[list[dict], int]:
    # API template_index is in the FULL labeled list, not the masked list.
    template = {p['cluster_index']: p for p in data['template']['points'] if p['label']}
    scene = {p['cluster_index']: p for p in data['scene']['points'] if p['label']}
    pairs, used_template, used_scene = [], set(), set()
    for record in records:
        left = template.get(record.get('template_index'))
        right = scene.get(record.get('scene_index'))
        if not left or not right or not store.labels_match(left['label'], right['label']):
            continue
        if left['id'] in used_template or right['id'] in used_scene:
            continue
        # Reject synthetic/recovered geometry that isn't the original OCR point.
        if not all(np.allclose(record.get(side, {}).get('center', [float('inf'), float('inf')]), [point['x'], point['y']], atol=.05, rtol=0)
                   for side, point in (('template', left), ('scene', right))):
            continue
        pairs.append({'template_id': left['id'], 'scene_id': right['id']})
        used_template.add(left['id'])
        used_scene.add(right['id'])
    return pairs, len(records) - len(pairs)


def predict(template: str, sample: str) -> dict:
    if not _RUN_LOCK.acquire(blocking=False):
        raise PredictionError('Another match prediction is running. Please try again when it finishes.')
    try:
        data = store.load_pair(template, sample)
        root = algorithm_root()
        version = algorithm_version(root)
        python = Path(os.getenv('OBJECT_DETECTION_PYTHON') or root / 'PythonPortable/env/bin/python')
        if not python.is_file():
            raise PredictionError('Object detection Python not found. Check OBJECT_DETECTION_PYTHON.')
        helper = Path(__file__).resolve().parents[1] / 'scripts/predict_ocr_matches.py'
        with tempfile.TemporaryDirectory(prefix='matches-predict-') as temporary:
            inputs = Path(temporary)
            template_path = store.template_folder(template)
            scene_path = store.folder(template, sample)
            (inputs / 'template').mkdir()
            for source, output, is_template in ((template_path, inputs / 'template/image.png', True), (scene_path, inputs / 'scene.png', False)):
                ocr = store.ocr_data(source)
                output.write_bytes(store.coordinate_image(source, ocr, template=is_template))
                target = inputs / ('template/ocr_character_overlay.json' if is_template else 'scene_ocr.json')
                target.write_text(json.dumps({'detections': ocr['detections']}))
            (inputs / 'template/bboxes.json').write_bytes((template_path / 'bboxes.json').read_bytes())
            # Detect input changes while copying, as well as during execution.
            if store.load_pair(template, sample)['fingerprints'] != data['fingerprints']:
                raise store.ConflictError('Inputs changed while preparing predictions. Reload and try again.')
            try:
                process = subprocess.run([str(python), str(helper), '--object-root', str(root), '--inputs', str(inputs)],
                                         cwd=root, capture_output=True, text=True,
                                         timeout=int(os.getenv('MATCHES_PREDICTION_TIMEOUT', '180')))
            except subprocess.TimeoutExpired as exc:
                raise PredictionError('Match prediction timed out. You can retry or continue matching manually.') from exc
            if process.returncode:
                raise PredictionError('Object detection matching failed: ' + (process.stderr or process.stdout)[-1500:])
            try:
                records = json.loads(process.stdout)['matches']
                if not isinstance(records, list):
                    raise ValueError('Invalid match list')
            except (ValueError, KeyError) as exc:
                raise PredictionError('Object detection returned an invalid prediction response.') from exc
        pairs, skipped = map_predictions(records, data)
        if store.load_pair(template, sample)['fingerprints'] != data['fingerprints'] or algorithm_version(root) != version:
            raise store.ConflictError('Inputs changed during prediction. Reload and try again.')
        payload = {'schema_version': 1, 'source': 'api_object_detection.obtain_matches',
                   'algorithm_version': version, 'fingerprints': data['fingerprints'],
                   'generated_at': datetime.now(timezone.utc).isoformat(), 'pairs': pairs,
                   'skipped': skipped, 'raw_match_count': len(records)}
        destination = store.folder(template, sample) / 'predicted_matches.json'
        fd, temporary = tempfile.mkstemp(prefix='.predictions-', suffix='.tmp', dir=destination.parent)
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(payload, stream, indent=2)
            os.replace(temporary, destination)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return payload
    finally:
        _RUN_LOCK.release()
