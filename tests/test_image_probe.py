# SPDX-License-Identifier: AGPL-3.0-only

import tempfile
import unittest
from pathlib import Path

from choice.image_probe import image_readable


def _tiny_png(path: Path) -> None:
    from PIL import Image

    Image.new("RGB", (2, 2), color="red").save(path)


class ImageProbeTests(unittest.TestCase):
    def test_zero_byte_not_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.jpg"
            path.write_bytes(b"")
            self.assertFalse(image_readable(path))

    def test_valid_png_readable(self):
        try:
            import PIL  # noqa: F401
        except ImportError:
            self.skipTest("Pillow not installed")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ok.png"
            _tiny_png(path)
            self.assertTrue(image_readable(path))

    def test_garbage_not_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.jpg"
            path.write_bytes(b"not an image")
            self.assertFalse(image_readable(path))

    def test_cache_by_mtime(self):
        try:
            import PIL  # noqa: F401
        except ImportError:
            self.skipTest("Pillow not installed")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ok.png"
            _tiny_png(path)
            self.assertTrue(image_readable(path))
            path.write_bytes(b"broken")
            self.assertFalse(image_readable(path))


if __name__ == "__main__":
    unittest.main()
