import base64
import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from src import matches_storage as store
from src.matches_router import router


class MatchesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'matches'
        self.patch = patch.object(store, 'MATCHES_ROOT', self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.env = patch.dict('os.environ', {'API_STORAGE_MODE': 'local', 'AUTH_MODE': 'local'})
        self.env.start()
        self.addCleanup(self.env.stop)
        templates = Path(self.temp.name) / 'templates'
        template_patch = patch.object(store, 'TEMPLATES_ROOT', templates)
        template_patch.start()
        self.addCleanup(template_patch.stop)
        self.template = templates / 'CI'
        self.scene = self.root / 'CI/sample'
        raw = BytesIO()
        Image.new('RGB', (100, 70), 'white').save(raw, format='PNG')
        self.image = raw.getvalue()
        detections = [{'text': label, 'poly': [[x, 10], [x+4, 10], [x+4, 18], [x, 18]], 'center': [99, 99]} for x, label in ((10, 'A'), (20, 'A'), (30, 'B'), (40, ''))]
        for folder in (self.template, self.scene):
            folder.mkdir(parents=True)
            (folder / 'ocr_character_overlay.json').write_text(json.dumps({'detections': detections, 'metadata': {'coordinates': 'rotated_image'}, 'rotated_image_base64': base64.b64encode(self.image).decode()}))
        (self.template / 'bboxes.json').write_text(json.dumps({'extract_text': [], 'noise': [], 'references': []}))
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)

    def payload(self, pairs=None):
        data = store.load_pair('CI', 'sample')
        return {'pairs': pairs or [{'template_id': 0, 'scene_id': 1}], 'revision': data['revision'], 'fingerprints': data['fingerprints']}

    def test_uses_api_polygon_centroids_and_rotated_image(self):
        data = store.load_pair('CI', 'sample')
        self.assertEqual(data['scene']['points'][0]['x'], 12)
        self.assertEqual(data['scene']['points'][0]['y'], 14)
        self.assertEqual(data['scene']['width'], 100)
        self.assertIsNone(data['scene']['points'][3]['cluster_index'])
        self.assertEqual(self.client.get('/matches/api/image/CI/sample/scene').content, self.image)

    def test_save_reload_and_conflict(self):
        payload = self.payload()
        response = self.client.put('/matches/api/pair/CI/sample', json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(store.load_pair('CI', 'sample')['pairs'], payload['pairs'])
        self.assertEqual(self.client.put('/matches/api/pair/CI/sample', json=payload).status_code, 409)
        self.assertEqual(store.catalog()[0]['samples'][0]['matches'], 1)
        self.assertEqual(len(list(self.scene.glob('*.tmp'))), 0)

    def test_rejects_invalid_pairs(self):
        for pairs in ([{'template_id':0,'scene_id':2}], [{'template_id':3,'scene_id':3}], [{'template_id':100,'scene_id':0}], [{'template_id':0,'scene_id':0},{'template_id':0,'scene_id':1}], [{'template_id':0,'scene_id':0},{'template_id':1,'scene_id':0}], [{'template_id':True,'scene_id':0}]):
            response = self.client.put('/matches/api/pair/CI/sample', json=self.payload(pairs))
            self.assertEqual(response.status_code, 422, response.text)
        self.assertFalse((self.scene / 'manual_matches.json').exists())

    def test_rejects_changed_ocr(self):
        payload = self.payload()
        self.assertEqual(self.client.put('/matches/api/pair/CI/sample', json=payload).status_code, 200)
        path = self.scene / 'ocr_character_overlay.json'
        doc = json.loads(path.read_text())
        doc['detections'][0]['text'] = 'Z'
        path.write_text(json.dumps(doc))
        self.assertEqual(self.client.get('/matches/api/pair/CI/sample').status_code, 409)

    def test_empty_annotations_can_be_saved(self):
        payload = self.payload()
        payload['pairs'] = []
        self.assertEqual(self.client.put('/matches/api/pair/CI/sample', json=payload).status_code, 200)
        self.assertTrue(store.catalog()[0]['samples'][0]['reviewed'])

    def test_auth_missing_and_traversal(self):
        with patch('src.matches_router.get_user', return_value=None):
            self.assertEqual(self.client.get('/matches/api/catalog').status_code, 401)
        for template, sample in (('..','sample'), ('CI','../outside'), ('_templates','CI')):
            with self.assertRaises(ValueError):
                store.folder(template, sample)
        self.assertEqual(self.client.get('/matches/api/pair/CI/missing').status_code, 404)
        self.assertEqual(self.client.get('/matches/assets/nope').status_code, 404)

    def test_page_and_assets_are_served(self):
        for url in ('/matches', '/matches/'):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertIn('id="board"', response.text)
        self.assertEqual(self.client.get('/matches/assets/matches.js').status_code, 200)

    def test_missing_rotated_image_does_not_fall_back_to_source(self):
        path = self.scene / 'ocr_character_overlay.json'
        doc = json.loads(path.read_text())
        doc.pop('rotated_image_base64')
        path.write_text(json.dumps(doc))
        (self.scene / 'input_image.png').write_bytes(self.image)
        self.assertEqual(self.client.get('/matches/api/pair/CI/sample').status_code, 404)

    def test_reads_live_template_and_excludes_extract_and_noise_only(self):
        legacy = self.root / '_templates/CI'
        legacy.mkdir(parents=True)
        (legacy / 'ocr_character_overlay.json').write_text('invalid unused snapshot')
        boxes = {
            'extract_text': [{'x': 9, 'y': 9, 'w': 7, 'h': 12}],
            'noise': [{'x': 29, 'y': 9, 'w': 7, 'h': 12}],
            'references': [{'x': 0, 'y': 0, 'w': 100, 'h': 70}],
        }
        (self.template / 'bboxes.json').write_text(json.dumps(boxes))
        data = store.load_pair('CI', 'sample')
        self.assertEqual([p['id'] for p in data['template']['points']], [1, 3])
        self.assertEqual(data['template']['excluded_point_count'], 2)
        self.assertEqual(data['template']['points'][0]['cluster_index'], 1)
        self.assertEqual(data['template']['points'][0]['matching_cluster_index'], 0)
        self.assertEqual([p['id'] for p in data['scene']['points']], [0, 1, 2, 3])
        self.assertEqual(self.client.put('/matches/api/pair/CI/sample', json=self.payload()).status_code, 422)
        self.assertEqual(self.client.put('/matches/api/pair/CI/sample', json=self.payload([{'template_id': 1, 'scene_id': 0}])).status_code, 200)

    def test_bbox_changes_recompute_mask_and_reject_stale_save(self):
        original = self.payload()
        (self.template / 'bboxes.json').write_text(json.dumps({'noise': [{'x': 9, 'y': 9, 'w': 7, 'h': 12}]}))
        current = store.load_pair('CI', 'sample')
        self.assertNotEqual(original['fingerprints'], current['fingerprints'])
        self.assertNotIn(0, [p['id'] for p in current['template']['points']])
        self.assertEqual(self.client.put('/matches/api/pair/CI/sample', json=original).status_code, 409)

    def test_saved_annotations_reject_changed_mask(self):
        self.assertEqual(self.client.put('/matches/api/pair/CI/sample', json=self.payload()).status_code, 200)
        (self.template / 'bboxes.json').write_text(json.dumps({'noise': [{'x': 9, 'y': 9, 'w': 7, 'h': 12}]}))
        self.assertEqual(self.client.get('/matches/api/pair/CI/sample').status_code, 409)

    def test_mask_pixel_edges_rounding_and_separators_match_api(self):
        # Splitting before integer truncation leaves row 4 unmasked, as in the API.
        mask = store.template_keep_mask({'extract_text': [{'x': -2, 'y': 0, 'w': 7, 'h': 5, 'seps': [.5], 'θ': 45}],
                                        'references': [{'x': 0, 'y': 0, 'w': 10, 'h': 10}]}, 10, 10)
        self.assertEqual(int(mask[3, 4]), 0)
        self.assertEqual(int(mask[4, 4]), 255)
        self.assertEqual(int(mask[3, 5]), 255)
        pts = [{'id': i, 'label': 'A', 'x': x, 'y': y} for i, (x, y) in enumerate([(4.49, 3), (4.51, 3), (2, 4), (10, 5), (-1, 5)])]
        self.assertEqual([p['id'] for p in store.filter_template_points(pts, mask)], [1, 2])

    def test_missing_bbox_file_is_reported(self):
        (self.template / 'bboxes.json').unlink()
        self.assertEqual(self.client.get('/matches/api/pair/CI/sample').status_code, 404)

    def test_catalog_ignores_error_reports_and_template_snapshots(self):
        (self.root / 'CI/failed.error.json').write_text('{}')
        rows = store.catalog()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['error_count'], 1)
        self.assertEqual(len(rows[0]['samples']), 1)

    def test_allows_equivalent_ocr_characters(self):
        left = store.load_pair('CI', 'sample')
        self.assertEqual(left['template']['points'][0]['label'], 'A')
        self.assertEqual(left['scene']['points'][0]['label'], 'A')

        template_doc = json.loads((self.template / 'ocr_character_overlay.json').read_text())
        scene_doc = json.loads((self.scene / 'ocr_character_overlay.json').read_text())
        template_doc['detections'][0]['text'] = 'o'
        scene_doc['detections'][0]['text'] = '0'
        template_doc['detections'][1]['text'] = 'i'
        scene_doc['detections'][1]['text'] = 'l'
        (self.template / 'ocr_character_overlay.json').write_text(json.dumps(template_doc))
        (self.scene / 'ocr_character_overlay.json').write_text(json.dumps(scene_doc))

        payload = self.payload([
            {'template_id': 0, 'scene_id': 0},
            {'template_id': 1, 'scene_id': 1},
        ])
        response = self.client.put('/matches/api/pair/CI/sample', json=payload)
        self.assertEqual(response.status_code, 200, response.text)


if __name__ == '__main__':
    unittest.main()
