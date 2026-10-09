# SPDX-License-Identifier: AGPL-3.0-only

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from choice.httpd import ChoiceSite
from choice.media import _pillow_ready, prepare_file
from tests.test_media_phone import _big_png


class MediaCacheConcurrentTests(unittest.TestCase):
    def test_parallel_prepare_file_no_errors(self):
        if not _pillow_ready():
            self.skipTest("Pillow not installed")
        with tempfile.TemporaryDirectory() as tmpname:
            tmp = Path(tmpname)
            src = tmp / "card.png"
            _big_png(src)
            cache = tmp / "cache"
            errors: list[BaseException] = []

            def one() -> None:
                try:
                    prepare_file(src, cache, etag_version="race")
                except BaseException as exc:
                    errors.append(exc)

            threads = [threading.Thread(target=one) for _ in range(24)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=60.0)
            self.assertEqual(errors, [])

    def test_parallel_media_http_no_500(self):
        if not _pillow_ready():
            self.skipTest("Pillow not installed")
        with tempfile.TemporaryDirectory() as tmpname:
            tmp = Path(tmpname)
            (tmp / "deck.json").write_text(
                json.dumps(
                    {
                        "source": {"type": "images", "path": ".", "recursive": True},
                        "directions": {"right": {"label": "Keep", "value": "keep"}},
                    }
                ),
                encoding="utf-8",
            )
            rel = "incoming/card.png"
            (tmp / "incoming").mkdir()
            _big_png(tmp / rel)
            ChoiceSite.allow_reuse_address = True
            server = ChoiceSite(("127.0.0.1", 0), tmp)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            port = server.server_address[1]
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/index", timeout=10
            ) as resp:
                index = json.loads(resp.read().decode("utf-8"))
            deck_id = index["decks"][0]["id"]
            item_id = rel.replace("\\", "/")
            url = (
                f"http://127.0.0.1:{port}/api/decks/{deck_id}/media?"
                f"item={urllib.parse.quote(item_id)}"
            )
            errors: list[int] = []

            def fetch() -> None:
                try:
                    with urllib.request.urlopen(url, timeout=30) as resp:
                        if resp.status >= 500:
                            errors.append(resp.status)
                except urllib.error.HTTPError as exc:
                    if exc.code >= 500:
                        errors.append(exc.code)

            threads = [threading.Thread(target=fetch) for _ in range(24)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=60.0)
            server.shutdown()
            self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
