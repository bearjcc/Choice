# SPDX-License-Identifier: AGPL-3.0-only

"""Media responses must be cacheable (ETag + Cache-Control) and honour If-None-Match."""

import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from choice.httpd import ChoiceSite
from choice.open import open_config

FIX = Path(__file__).resolve().parent / "fixtures" / "plugin_host"


class MediaHttpCacheTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        os.environ["CHOICE_DISABLE_WARM"] = "1"
        cfg = self.tmp / "choice.toml"
        cfg.write_text(
            f"""
[state]
dir = "state"

[[sources]]
id = "swipe"
type = "swipe"
path = "{FIX.as_posix()}"

[[decks]]
id = "d"
title = "D"
source = "swipe"
mount = "gallery"
""".strip(),
            encoding="utf-8",
        )
        self.cfg = cfg

    def tearDown(self):
        os.environ.pop("CHOICE_DISABLE_WARM", None)
        self._tmp.cleanup()

    def _get_raw(self, port: int, path: str, headers: dict | None = None):
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=10) as res:
                return res.status, res.read(), dict(res.headers)
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read(), dict(exc.headers)

    def test_media_etag_and_304(self):
        ChoiceSite.allow_reuse_address = True
        server = ChoiceSite(("127.0.0.1", 0), self.tmp, config_path=self.cfg)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/decks/d/items?pending=1&limit=5", timeout=10
            ) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            item_id = body["items"][0]["id"]
            path = f"/api/decks/d/media?item={urllib.parse.quote(item_id)}&w=1280"
            status, _payload, headers = self._get_raw(port, path)
            self.assertEqual(status, 200)
            etag = headers.get("ETag") or headers.get("etag")
            self.assertTrue(etag, headers)
            cache = headers.get("Cache-Control") or headers.get("cache-control") or ""
            self.assertIn("max-age", cache.lower())
            status2, body2, _h2 = self._get_raw(port, path, {"If-None-Match": etag})
            self.assertEqual(status2, 304)
            self.assertEqual(body2, b"")
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
