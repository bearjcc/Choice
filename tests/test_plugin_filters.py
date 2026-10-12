# SPDX-License-Identifier: AGPL-3.0-only

import json
import os
import tempfile
import threading
import unittest
import urllib.parse
import urllib.request
from pathlib import Path

from choice.httpd import ChoiceSite
from choice.open import open_config
from choice.plugin_filters import (
    decode_filter_param,
    encode_filter_param,
    selection_to_plugin_filter,
)
from choice.plugin_pool import clear_pool

FIX = Path(__file__).resolve().parent / "fixtures" / "plugin_host"


class PluginFilterTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        os.environ["CHOICE_DISABLE_WARM"] = "1"
        clear_pool()

    def tearDown(self):
        clear_pool()
        os.environ.pop("CHOICE_DISABLE_WARM", None)
        self._tmp.cleanup()

    def _config(self, mount: str) -> Path:
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
mount = "{mount}"
""".strip(),
            encoding="utf-8",
        )
        return cfg

    def test_selection_to_plugin_filter(self):
        sel = {"tag": {"values": ["a"], "match": "all"}, "_sort": "title"}
        out = selection_to_plugin_filter(sel)
        self.assertEqual(out, {"tag": {"values": ["a"], "match": "all"}, "_sort": "title"})
        self.assertIsNone(selection_to_plugin_filter({}))
        roundtrip = decode_filter_param(encode_filter_param(sel))
        self.assertEqual(roundtrip, sel)

    def test_list_items_respects_filter_param(self):
        from choice.deck_cache import load_items as cached_load_items
        from choice.plugin_filters import reset_request_filter, set_request_filter

        deck = open_config(self._config("filtered_list")).decks[0]
        items, _w = cached_load_items(deck)
        self.assertEqual(len(items), 3)
        token = set_request_filter({"tag": {"values": ["b"]}})
        try:
            items2, _w2 = cached_load_items(deck)
        finally:
            reset_request_filter(token)
        self.assertEqual([i.id for i in items2], ["2", "3"])

    def test_http_items_and_stats_with_f(self):
        cfg = self._config("filtered_list")
        ChoiceSite.allow_reuse_address = True
        server = ChoiceSite(("127.0.0.1", 0), self.tmp, config_path=cfg)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        f = encode_filter_param({"tag": {"values": ["a"], "match": "any"}})
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/decks/d/filters", timeout=10
            ) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(body.get("ok"))
            self.assertIn("filters", body)
            self.assertEqual(body["filters"]["filters"][0]["id"], "tag")
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/decks/d/items?pending=1&limit=10&f={urllib.parse.quote(f)}",
                timeout=10,
            ) as resp:
                items = json.loads(resp.read().decode("utf-8"))
            self.assertEqual([row["id"] for row in items["items"]], ["1", "2"])
            self.assertIn("plugin_filters", items)
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/decks/d/stats?f={urllib.parse.quote(f)}",
                timeout=10,
            ) as resp:
                stats = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(stats["stats"]["match_count"], 2)
            self.assertEqual(stats["stats"]["hint"], "filtered")
        finally:
            server.shutdown()
            server.server_close()

    def test_legacy_plugin_ignores_unknown_f(self):
        cfg = self._config("list_counter")
        ChoiceSite.allow_reuse_address = True
        server = ChoiceSite(("127.0.0.1", 0), self.tmp, config_path=cfg)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        f = encode_filter_param({"nope": {"values": ["x"]}})
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/decks/d/items?pending=1&limit=5&f={urllib.parse.quote(f)}",
                timeout=10,
            ) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(body.get("ok"))
            self.assertGreaterEqual(len(body.get("items") or []), 1)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
