import tempfile
import unittest
from pathlib import Path

from ocr_showcase.__main__ import copy_unique, extract_fields, safe_filename


class WorkflowTests(unittest.TestCase):
    def test_fields_in_table(self):
        text = "Собственник: Иванов Иван Иванович\nВид помещения Номер помещения Площадь Доля\nквартира 271 69,7 1"
        result = extract_fields(text, 87.2)
        self.assertEqual(result.fio, "Иванов Иван Иванович")
        self.assertEqual(result.room, "271")

    def test_filename_rejects_path_input(self):
        with self.assertRaises(ValueError):
            safe_filename("Иванов Иван Иванович", "../../secret")

    def test_duplicate_does_not_replace_or_remove_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "input.pdf"
            source.write_bytes(b"test")
            first = copy_unique(source, root / "ready", "Иванов Иван Иванович (12).pdf")
            second = copy_unique(source, root / "ready", "Иванов Иван Иванович (12).pdf")
            self.assertNotEqual(first, second)
            self.assertEqual(first.read_bytes(), b"test")
            self.assertEqual(second.read_bytes(), b"test")
            self.assertTrue(source.exists())


if __name__ == "__main__":
    unittest.main()
