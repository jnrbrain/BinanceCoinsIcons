import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from PIL import Image
import coin_logo_downloader as downloader


class LogoTests(unittest.TestCase):
    def test_manifest_changes_only_with_valid_image_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / 'manifest.json'
            icon = root / 'MAGMA.png'
            Image.new('RGBA', (64, 64), 'red').save(icon)
            (root / 'BAD.png').write_bytes(b'bad')
            first = downloader.write_manifest(root, target)
            self.assertEqual(list(first), ['MAGMA'])
            original = target.read_bytes()
            downloader.write_manifest(root, target)
            self.assertEqual(original, target.read_bytes())
            Image.new('RGBA', (64, 64), 'blue').save(icon)
            self.assertNotEqual(first['MAGMA'], downloader.write_manifest(root, target)['MAGMA'])

    def test_exact_symbol_precedes_multiplier_alias(self):
        self.assertEqual(downloader.candidates("1000RATS", {"1000RATS": ["exact"], "RATS": ["base"]}), ["exact", "base"])

    def test_digit_names_are_not_blindly_stripped(self):
        logos = {"1INCH": ["inch"], "4": ["four"], "INCH": ["wrong"]}
        self.assertEqual(downloader.candidates("1INCH", logos), ["inch"])
        self.assertEqual(downloader.candidates("4", logos), ["four"])

    def test_corrupt_existing_file_is_not_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "BTC.png"
            path.write_bytes(b"bad image")
            self.assertFalse(downloader.valid_icon(path))
            Image.new("RGBA", (64, 64)).save(path)
            self.assertTrue(downloader.valid_icon(path))


if __name__ == "__main__":
    unittest.main()
