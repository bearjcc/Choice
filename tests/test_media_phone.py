# SPDX-License-Identifier: AGPL-3.0-only

import tempfile
import unittest
from pathlib import Path

from choice.media import (
    _pillow_ready,
    prepare_bytes,
    prepare_file,
    sweep_cache,
)


def _big_png(path: Path, size: tuple[int, int] = (2400, 1600)) -> None:
    if _pillow_ready():
        from PIL import Image

        image = Image.new("RGB", size, (120, 80, 200))
        image.save(path, "PNG")
        return
    # minimal valid PNG header plus padding
    base = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
    )
    path.write_bytes(base + b"\0" * 200_000)


class MediaPhoneTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.cache = self.tmp / "media_cache"

    def tearDown(self):
        self._tmp.cleanup()

    @unittest.skipUnless(_pillow_ready(), "Pillow not installed")
    def test_file_resize_caches_smaller_copy(self):
        src = self.tmp / "huge.png"
        _big_png(src)
        original = src.stat().st_size
        served = prepare_file(src, self.cache, etag_version="t1")
        self.assertIsNotNone(served.path)
        assert served.path is not None
        self.assertLess(served.path.stat().st_size, original)
        again = prepare_file(src, self.cache, etag_version="t1")
        self.assertEqual(served.path, again.path)

    @unittest.skipUnless(_pillow_ready(), "Pillow not installed")
    def test_full_serves_original_file(self):
        src = self.tmp / "huge.png"
        _big_png(src)
        original = src.stat().st_size
        served = prepare_file(src, self.cache, full=True, etag_version="t1")
        self.assertEqual(served.path, src.resolve())
        payload = served.path.read_bytes() if served.path else served.data
        self.assertEqual(len(payload), original)

    @unittest.skipUnless(_pillow_ready(), "Pillow not installed")
    def test_bytes_resize_and_cache(self):
        src = self.tmp / "huge.png"
        _big_png(src)
        raw = src.read_bytes()
        identity = "deck|item|-|-|token"
        served = prepare_bytes(raw, "image/png", self.cache, identity, etag_version="token")
        self.assertIsNotNone(served.path or served.data)
        if served.path:
            self.assertLess(served.path.stat().st_size, len(raw))
        served2 = prepare_bytes(raw, "image/png", self.cache, identity, etag_version="token")
        self.assertEqual(served.path, served2.path)

    def test_sweep_drops_old_cache_files(self):
        self.cache.mkdir()
        old = self.cache / "dead.webp"
        old.write_bytes(b"x" * 1000)
        import os
        import time

        os.utime(old, (time.time() - 40 * 86400, time.time() - 40 * 86400))
        sweep_cache(self.cache)
        self.assertFalse(old.exists())

    @unittest.skipUnless(_pillow_ready(), "Pillow not installed")
    def test_width_query_limits_edge(self):
        src = self.tmp / "wide.png"
        _big_png(src, (3000, 1000))
        served = prepare_file(src, self.cache, width=400, etag_version="w")
        assert served.path is not None
        from PIL import Image

        with Image.open(served.path) as image:
            self.assertLessEqual(max(image.size), 640)

    def test_no_pillow_returns_original_bytes(self):
        from unittest.mock import patch

        raw = b"\xff\xd8\xff" + b"x" * 5000
        with patch("choice.media._pillow_ready", return_value=False):
            served = prepare_bytes(raw, "image/jpeg", self.cache, "id", etag_version="1")
        self.assertEqual(served.data, raw)


if __name__ == "__main__":
    unittest.main()
