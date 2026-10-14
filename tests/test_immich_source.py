# SPDX-License-Identifier: AGPL-3.0-only

import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

from choice.act import decide, undo
from choice.media import prepare_bytes
from choice.open import open_config

WEBP = (
    b"\x52\x49\x46\x46\x24\x00\x00\x00WEBPVP8 \x18\x00\x00\x00\x2a\x01\x00\x9d\x01\x2a"
    b"\x01\x00\x01\x00\x02\x00\x34\x25\xa4\x00\x03\x70\x00\xfe\xfb\xfd\x50\x00"
)


def _start_mock_server(handler):
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _stop_mock_server(server, thread):
    server.shutdown()
    thread.join(timeout=10.0)
    server.server_close()


class _StableMockHandler(BaseHTTPRequestHandler):
    """One-shot HTTP/1.0 responses; avoids Windows keep-alive aborts (WinError 10053)."""

    protocol_version = "HTTP/1.0"

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass

    def _write_body(self, body: bytes) -> None:
        self.wfile.write(body)
        self.wfile.flush()

    def _json(self, code: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self._write_body(body)

    def _respond(self, code: int, content_type: str, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self._write_body(body)


class _ImmichMock(_StableMockHandler):
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
            "visibility": "hidden",
        },
    ]

    def log_message(self, fmt, *args):
        return

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/server/ping":
            return self._json(200, {"res": "ok"})
        if path.startswith("/api/assets/") and path.endswith("/thumbnail"):
            return self._respond(200, "image/webp", WEBP)
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
                from choice.sources.immich import _asset_visible

                items = [a for a in self.assets if _asset_visible(a, exclude_archived=True)]
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
        self.server, self.thread = _start_mock_server(_ImmichMock)
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
        _stop_mock_server(self.server, self.thread)
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

    def test_favourite_swipe_opt_in(self):
        deck = open_config(self.cfg).decks[0]
        self.assertNotIn("up", deck.directions)

    def test_video_shows_media(self):
        from choice.sources.immich import _item_from_asset

        item = _item_from_asset({"id": "v1", "originalFileName": "clip.mov", "type": "VIDEO"})
        self.assertTrue(item.public(None).get("media"))


class _PagingImmichMock(_ImmichMock):
    """Page 1: five rows, four archived; page 2: five more (one duplicate of page 1)."""

    search_pool = [
        {"id": "p1", "originalFileName": "1.jpg", "type": "IMAGE", "isArchived": True},
        {"id": "p2", "originalFileName": "2.jpg", "type": "IMAGE", "isArchived": True},
        {"id": "p3", "originalFileName": "3.jpg", "type": "IMAGE", "isArchived": True},
        {"id": "p4", "originalFileName": "4.jpg", "type": "IMAGE", "isArchived": True},
        {"id": "keep-a", "originalFileName": "a.jpg", "type": "IMAGE"},
        {"id": "keep-b", "originalFileName": "b.jpg", "type": "IMAGE"},
        {"id": "keep-c", "originalFileName": "c.jpg", "type": "IMAGE"},
        {"id": "keep-d", "originalFileName": "d.jpg", "type": "IMAGE"},
        {"id": "keep-e", "originalFileName": "e.jpg", "type": "IMAGE"},
        {"id": "dup-a", "originalFileName": "a-again.jpg", "type": "IMAGE"},
    ]

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/search/smart":
            self.send_response(404)
            self.end_headers()
            return
        body = self._read_json()
        if path == "/api/search/metadata" and body.get("description") == "tree":
            page = int(body.get("page") or 1)
            size = int(body.get("size") or 5)
            start = (page - 1) * size
            chunk = self.search_pool[start : start + size]
            if page == 2 and chunk:
                chunk = [chunk[0]] + self.search_pool[5:9]
            return self._json(
                200,
                {
                    "assets": {
                        "items": chunk,
                        "total": len(self.search_pool),
                        "page": page,
                    }
                },
            )
        self.send_response(404)
        self.end_headers()


class ImmichPagingTests(unittest.TestCase):
    def setUp(self):
        os.environ["IMMICH_API_KEY"] = "test"
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.server, self.thread = _start_mock_server(_PagingImmichMock)
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
id = "search"
title = "Search"
source = "imm"
mount = "search:tree"
page_size = 5
""".strip(),
            encoding="utf-8",
        )

    def tearDown(self):
        _stop_mock_server(self.server, self.thread)
        self._tmp.cleanup()

    def test_search_pages_no_duplicate_ids(self):
        deck = open_config(self.cfg).decks[0]
        items, _ = deck.load_items()
        ids = [item.id for item in items]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(ids), 5)
        self.assertNotIn("p1", ids)
