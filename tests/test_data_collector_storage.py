import unittest

from src.data_collector_storage import input_image_blob_name, item_blob_name, uploaded_filename


class DataCollectorStorageTests(unittest.TestCase):
    def test_item_blob_name_uses_original_filename(self) -> None:
        self.assertEqual(
            item_blob_name("CI", "tk_12657165_CI__img1.png", "abc123"),
            "CI/tk_12657165_CI__img1",
        )

    def test_item_blob_name_removes_directories_and_unsafe_characters(self) -> None:
        self.assertEqual(
            item_blob_name("CI/forms", r"C:\uploads\bad:name?.png", "abc123"),
            "CI-forms/bad-name-",
        )

    def test_item_blob_name_adds_hash_only_for_collision(self) -> None:
        occupied = {"CI/invoice"}
        self.assertEqual(
            item_blob_name("CI", "invoice.png", "abcdef123456", occupied),
            "CI/invoice-abcdef12",
        )

    def test_uploaded_filename_has_hash_fallback(self) -> None:
        self.assertEqual(uploaded_filename("", "abcdef1234567890"), "image-abcdef1234567890")

    def test_input_image_blob_name_preserves_image_format(self) -> None:
        self.assertEqual(
            input_image_blob_name("user", "data_collector", "CI/invoice.png", "PNG"),
            "user/data_collector/CI/invoice.png/input_image.png",
        )

    def test_input_image_blob_name_sanitizes_the_extension(self) -> None:
        self.assertEqual(
            input_image_blob_name("user", "data_collector", "CI/invoice", "../JpEg"),
            "user/data_collector/CI/invoice/input_image.jpeg",
        )


if __name__ == "__main__":
    unittest.main()
