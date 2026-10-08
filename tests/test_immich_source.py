# SPDX-License-Identifier: AGPL-3.0-only

import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from choice.act import decide, undo
from choice.media import prepare_bytes
from choice.open import open_config

WEBP = (
    b"\x52\x49\x46\x46\x24\x00\x00\x00WEBPVP8 \x18\x00\x00\x00\x2a\x01\x00\x9d\x01\x2a"
    b"\x01\x00\x01\x00\x02\x00\x34\x25\xa4\x00\x03\x70\x00\xfe\xfb\xfd\x50\x00"
)


class _ImmichMock(BaseHTTPRequestHandler):
    album_id = "album-1"
    assets = [
        {
            "id": "asset-a",
            "originalFileName": "a.jpg",
            "type": "IMAGE",
            "isArchived": False,
        },
        {
            "id": "asset-b",
            "originalFileName": "b.jpg",
            "type": "IMAGE",
            "isHidden": True,
        },
    ]

    def log_message(self, fmt, *args):
        return

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _json(self, code: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/server/ping":
            return self._json(200, {"res": "ok"})
        if path.startswith("/api/assets/") and path.endswith("/thumbnail"):
            self.send_response(200)
            self.send_header("Content-Type", "image/webp")
            self.send_header("Content-Length", str(len(WEBP)))
            self.end_headers()
            self.wfile.write(WEBP)
            return
        if path.startswith("/api/assets/"):
            aid = path.split("/")[-1]
            row = next((a for a in self.assets if a["id"] == aid), None)
            if row is None:
                self.send_response(404)
                self.end_headers()
                return
            return self._json(200, {**row, "isFavorite": False})
        if path == f"/api/albums/{self.album_id}":
            return self._json(200, {"id": self.album_id, "assetCount": 1})
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path
        body = self._read_json()
        if path == "/api/search/metadata":
            if self.album_id in (body.get("albumIds") or []):
                items = [a for a in self.assets if not a.get("isHidden")]
                return self._json(
                    200,
                    {"assets": {"items": items, "total": len(items), "page": body.get("page", 1)}},
                )
            return self._json(200, {"assets": {"items": [], "total": 0}})
        if path == "/api/search/smart":
            self.send_response(404)
            self.end_headers()
            return
        if path == "/api/trash/restore/assets":
            return self._json(200, {"count": len(body.get("ids") or [])})
        self.send_response(404)
        self.end_headers()

    def do_DELETE(self):
        path = urlparse(self.path).path
        if path == "/api/assets":
            self.send_response(204)
            self.end_headers()
            return
        self.send_response(404)
        self.end_headers()

    def do_PUT(self):
        path = urlparse(self.path).path
        if path == "/api/assets":
            return self._json(200, {"ids": self._read_json().get("ids") or []})
        self.send_response(404)
        self.end_headers()


class ImmichSourceTests(unittest.TestCase):
    def setUp(self):
        os.environ["IMMICH_API_KEY"] = "test"
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _ImmichMock)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.cfg = self.tmp / "choice.toml"
        self.cfg.write_text(
            f"""
[state]
dir = "state"

[[sources]]
id = "imm"
type = "immich"
url = "{self.base}"
api_key = "IMMICH_API_KEY"

[[decks]]
id = "album"
title = "Album"
source = "imm"
mount = "album:album-1"
""".strip(),
            encoding="utf-8",
        )

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self._tmp.cleanup()

    def test_album_lists_via_metadata_search(self):
        deck = open_config(self.cfg).decks[0]
        items, _warnings = deck.load_items()
        self.assertEqual([item.id for item in items], ["asset-a"])
        pub = items[0].public(None)
        self.assertTrue(pub.get("media"))
        self.assertTrue(items[0].plugin_media)

    def test_media_bytes_accepts_item_kwarg(self):
        deck = open_config(self.cfg).decks[0]
        items, _ = deck.load_items()
        plugin = deck.plugin
        blob = plugin.media_bytes(items[0].id, item=items[0].plugin_row, index=0)
        self.assertIsNotNone(blob)
        self.assertEqual(blob[1], "image/webp")

    def test_trash_delete_204_and_undo_restore(self):
        deck = open_config(self.cfg).decks[0]
        items, _ = deck.load_items()
        result = decide(deck, items[0].id, "left", "")
        self.assertTrue(result["ok"])
        restored = undo(deck)
        self.assertTrue(restored["ok"])

    def test_error_message_includes_immich_text(self):
        import urllib.error

        from choice.sources.immich import _http_problem

        body = json.dumps({"message": "bad album"}).encode("utf-8")
        err = urllib.error.HTTPError(
            self.base, 400, "Bad Request", hdrs=None, fp=__import__("io").BytesIO(body)
        )
        problem = _http_problem(err)
        self.assertIn("HTTP 400", str(problem))
        self.assertIn("bad album", str(problem))

    def test_webp_resize_etag(self):
        deck = open_config(self.cfg).decks[0]
        items, _ = deck.load_items()
        cache = deck.state_dir / "media_cache"
        identity = f"{deck.id}|{items[0].id}|-|-|{items[0].media_token}"
        served = prepare_bytes(
            WEBP,
            "image/webp",
            cache,
            identity,
            etag_version=items[0].media_token,
        )
        self.assertTrue(served.etag)
        self.assertTrue(served.path or served.data)
