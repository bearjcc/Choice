# SPDX-License-Identifier: AGPL-3.0-only

import json
import os
import tempfile
import threading
import unittest
import urllib.parse
import urllib.request
from pathlib import Path

from choice.act import progress
from choice.deck_cache import load_items as cached_load_items
from choice.deck_index import clear_index, record_items, snapshot
from choice.httpd import ChoiceSite
from choice.load import Item
from choice.open import open_config
from choice.plugin_filters import (
    encode_filter_param,
    reset_request_filter,
    set_request_filter,
)

FIX = Path(__file__).resolve().parent / "fixtures" / "plugin_host"


class PluginFilterSnapshotTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        os.environ["CHOICE_DISABLE_WARM"] = "1"

    def tearDown(self):
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

    def test_snapshot_keyed_by_filter(self):
        deck = open_config(self._config("filtered_list")).decks[0]
        clear_index(deck)
        token = set_request_filter({"tag": {"values": ["a"], "match": "any"}})
        try:
            items, _ = cached_load_items(deck)
            self.assertEqual({i.id for i in items}, {"1", "2"})
            snap_a = snapshot(deck)
            self.assertIsNotNone(snap_a)
            self.assertEqual(set(snap_a.order), {"1", "2"})
        finally:
            reset_request_filter(token)

        token_b = set_request_filter({"tag": {"values": ["b"], "match": "any"}})
        try:
            self.assertIsNone(snapshot(deck))
            items_b, _ = cached_load_items(deck)
            self.assertEqual({i.id for i in items_b}, {"2", "3"})
            snap_b = snapshot(deck)
            self.assertEqual(set(snap_b.order), {"2", "3"})
        finally:
            reset_request_filter(token_b)

    def test_progress_page_not_stale_after_filter_switch(self):
        deck = open_config(self._config("filtered_list")).decks[0]
        clear_index(deck)
        token = set_request_filter({"tag": {"values": ["a"], "match": "any"}})
        try:
            cached_load_items(deck)
        finally:
            reset_request_filter(token)

        token2 = set_request_filter({"tag": {"values": ["zzz"], "match": "any"}})
        try:
            page = progress(deck, pending=True, limit=20)
            self.assertTrue(page.get("ok"))
            self.assertEqual(page.get("items") or [], [])
        finally:
            reset_request_filter(token2)

    def test_empty_filter_result_not_replaced_by_snapshot(self):
        deck = open_config(self._config("chaotic_list")).decks[0]
        clear_index(deck)
        record_items(
            deck,
            [
                Item(
                    id="cached",
                    kind="card",
                    title="Cached",
                    body="",
                    fields={},
                )
            ],
        )
        deck.plugin.obj._mode = "empty"
        token = set_request_filter({"tag": {"values": ["x"]}})
        try:
            items, warnings = deck.load_items()
        finally:
            reset_request_filter(token)
        self.assertEqual(items, [])
        self.assertFalse(any("last good" in w.lower() for w in warnings))

    def test_http_empty_filter_stats_and_items(self):
        cfg = self._config("filtered_list")
        ChoiceSite.allow_reuse_address = True
        server = ChoiceSite(("127.0.0.1", 0), self.tmp, config_path=cfg)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        f = encode_filter_param({"tag": {"values": ["zzz"], "match": "any"}})
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/decks/d/items?pending=1&limit=10&f={urllib.parse.quote(f)}",
                timeout=10,
            ) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(body.get("items") or [], [])
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/decks/d/stats?f={urllib.parse.quote(f)}",
                timeout=10,
            ) as resp:
                stats = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(stats["stats"]["match_count"], 0)
            self.assertEqual(stats["stats"]["hint"], "filtered")
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
