# SPDX-License-Identifier: AGPL-3.0-only

import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from choice.config import load_config, save_config
from choice.httpd import ChoiceSite
from choice.image_delivery import preview_transcode, variant_cache_path
from choice.server_settings import ImageDeliverySettings, merge_server_patch, parse_server_settings

FIX = Path(__file__).resolve().parent / "fixtures" / "plugin_host"


class ServerSettingsTests(unittest.TestCase):
    def test_round_trip_toml(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "choice.toml"
            path.write_text(
                f"""
[state]
dir = "state"

[[sources]]
id = "s"
type = "swipe"
path = "{FIX.as_posix()}"

[[decks]]
id = "d"
title = "D"
source = "s"
mount = "filtered_list"

[network]
host = "0.0.0.0"
port = 9001
trust_forwarded = true

[http]
compress = "brotli"

[images]
transcode = true
format = "webp"
max_edge = 1600
""",
                encoding="utf-8",
            )
            cfg = load_config(path)
            self.assertEqual(cfg.server.network.port, 9001)
            self.assertTrue(cfg.server.network.trust_forwarded)
            self.assertEqual(cfg.server.http.compress, "brotli")
            self.assertTrue(cfg.server.images.transcode)
            sources = [{"id": "s", "type": "swipe", "path": str(FIX)}]
            decks = [{"id": "d", "title": "D", "source": "s", "mount": "filtered_list"}]
            save_config(cfg, sources, decks)
            again = load_config(path)
            self.assertEqual(again.server.network.port, 9001)
            self.assertEqual(again.server.http.compress, "brotli")

    def test_merge_patch_validates(self):
        base = parse_server_settings({})
        merged = merge_server_patch(base, {"http": {"compress": "gzip"}})
        self.assertEqual(merged.http.compress, "gzip")


class ImageDeliveryCacheTests(unittest.TestCase):
    def test_variant_key_changes_with_mtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "a.jpg"
            src.write_bytes(b"fake")
            profile = ImageDeliverySettings(transcode=True, format="webp")
            p1 = variant_cache_path(Path(tmp) / "cache", src, profile)
            src.write_bytes(b"fake2")
            p2 = variant_cache_path(Path(tmp) / "cache", src, profile)
            self.assertNotEqual(p1, p2)

    def test_preview_fallback_without_pillow(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "a.bin"
            src.write_bytes(b"not-an-image")
            profile = ImageDeliverySettings(transcode=True, format="webp")
            out = preview_transcode(src, profile)
            self.assertIn("ok", out)


class AdminOwnerTests(unittest.TestCase):
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
id = "s"
type = "swipe"
path = "{FIX.as_posix()}"

[[decks]]
id = "d"
title = "D"
source = "s"
mount = "filtered_list"
""",
            encoding="utf-8",
        )
        users = self.tmp / ".choice" / "users.json"
        users.parent.mkdir(parents=True)
        users.write_text(
            json.dumps(
                {
                    "owner": "alice",
                    "users": [
                        {"id": "alice", "name": "Alice", "decks": "*"},
                        {"id": "bob", "name": "Bob", "decks": "*"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        ChoiceSite.allow_reuse_address = True
        self.server = ChoiceSite(("127.0.0.1", 0), self.tmp, config_path=cfg)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        os.environ.pop("CHOICE_DISABLE_WARM", None)
        self._tmp.cleanup()

    def _get(self, path: str):
        return urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=10)

    def test_non_owner_forbidden(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._get("/api/admin/server?user=bob")
        self.assertEqual(ctx.exception.code, 403)

    def test_owner_can_read(self):
        with self._get("/api/admin/server?user=alice") as resp:
            body = json.loads(resp.read().decode())
        self.assertTrue(body["ok"])
        self.assertIn("settings", body)

    def test_owner_config_schema(self):
        with self._get("/api/admin/config-schema?user=alice") as resp:
            body = json.loads(resp.read().decode())
        self.assertTrue(body["ok"])
        self.assertIn("fields", body)
        self.assertIn("not_exposed", body)
        keys = {f["key"] for f in body["fields"]}
        self.assertIn("network.host", keys)
        self.assertIn("decks.mount", keys)
