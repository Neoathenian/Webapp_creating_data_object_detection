import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import gcs_storage as storage
from scripts.migrate_local_storage import migrate


class LocalStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "outputs" / "local"
        self.patch = patch.object(storage, "LOCAL_STORAGE_DIR", self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.env = patch.dict("os.environ", {"API_STORAGE_MODE": "local"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_template_and_collector_round_trip(self):
        template = {"id": "template", "image_blob": "user/CI/image.png"}
        collector = {"id": "item", "kind": "data_collector"}
        storage.upload_bytes(json.dumps(template).encode(), "user/CI/bboxes.json")
        storage.upload_bytes(json.dumps(collector).encode(), "user/data_collector/CI/photo/bboxes.json")
        storage.upload_bytes(b"image", template["image_blob"])
        self.assertTrue((self.root / "templates/CI/bboxes.json").exists())
        self.assertTrue((self.root / "bboxes/CI/photo/bboxes.json").exists())
        self.assertEqual(storage.download_bytes(template["image_blob"]), b"image")
        self.assertTrue(storage.blob_exists(template["image_blob"]))
        self.assertTrue(storage.is_name_taken("user", "CI"))
        self.assertEqual({doc["id"] for doc in storage.iter_user_docs("user")}, {"template", "item"})
        self.assertEqual(storage.find_doc_by_name("user", "CI"), (template, "user/CI/bboxes.json"))
        found, blob = storage.find_doc_by_id("user", "item")
        self.assertEqual(found, collector)
        self.assertEqual(json.loads(storage.download_bytes(blob)), collector)
        storage.copy_blob("user/CI/image.png", "user/Talon/image.png", delete_src=True)
        self.assertFalse(storage.blob_exists("user/CI/image.png"))
        self.assertEqual(storage.download_bytes("user/Talon/image.png"), b"image")
        self.assertEqual(storage.delete_prefix("user/data_collector/CI/photo/"), 1)
        self.assertIsNone(storage.find_doc_by_id("user", "item"))
        self.assertTrue(storage.is_name_taken("user", "CI"))

    def test_migration_preserves_saved_references(self):
        old = Path(self.temp.name) / "local_storage"
        for key in ("user/CI/image.png", "user/Talon/image.png", "user/data_collector/CI/photo/input_image.png"):
            path = old / key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(key.encode())
        self.assertEqual(migrate(old, self.root, dry_run=True), 3)
        self.assertFalse(self.root.exists())
        self.assertEqual(migrate(old, self.root), 3)
        self.assertFalse(old.exists())
        for key in ("user/CI/image.png", "user/Talon/image.png", "user/data_collector/CI/photo/input_image.png"):
            self.assertEqual(storage.download_bytes(key), key.encode())

    def test_migration_refuses_collisions_before_moving(self):
        old = Path(self.temp.name) / "local_storage"
        for uid in ("user1", "user2"):
            (old / uid / "CI").mkdir(parents=True)
        with self.assertRaises(FileExistsError):
            migrate(old, self.root)
        self.assertTrue((old / "user1/CI").exists())
        self.assertFalse(self.root.exists())

    def test_rejects_parent_traversal(self):
        with self.assertRaises(ValueError):
            storage.upload_bytes(b"bad", "user/CI/../../outside")


if __name__ == "__main__":
    unittest.main()
