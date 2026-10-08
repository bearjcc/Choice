# SPDX-License-Identifier: AGPL-3.0-only

import json
import os
import tempfile
import unittest
from pathlib import Path

from choice.act import _read_log, decide, index_summary, progress, run_plugin_action
from choice.deck_index import clear_index
from choice.open import open_config
from choice.plugin_pool import clear_pool
from choice.swipe_plugin import SwipePlugin

FIX = Path(__file__).resolve().parent / "fixtures" / "plugin_host"


class PluginHostTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        os.environ["CHOICE_DISABLE_WARM"] = "1"
        clear_pool()
        os.environ.pop("INSTANCE_COUNTER_PATH", None)
        os.environ.pop("LIST_COUNTER_PATH", None)
        os.environ.pop("MEDIA_ROW_PATH", None)
        os.environ.pop("ACTION_COUNTER_PATH", None)

    def tearDown(self):
        clear_pool()
        os.environ.pop("CHOICE_DISABLE_WARM", None)
        self._tmp.cleanup()

    def _config(self, mount: str, extra: str = "") -> Path:
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
{extra}
""".strip(),
            encoding="utf-8",
        )
        return cfg

    def _deck(self, mount: str, extra: str = ""):
        return open_config(self._config(mount, extra)).decks[0]

    def test_plugin_instance_reused(self):
        counter = self.tmp / "instances.txt"
        os.environ["INSTANCE_COUNTER_PATH"] = str(counter)
        cfg = self._config("instance_counter")
        d1 = open_config(cfg).decks[0]
        d2 = open_config(cfg).decks[0]
        d1.load_items()
        d2.load_items()
        self.assertEqual(counter.read_text(encoding="utf-8").strip(), "1")

    def test_index_skips_list_items_without_snapshot(self):
        counter = self.tmp / "lists.txt"
        os.environ["LIST_COUNTER_PATH"] = str(counter)
        deck = self._deck("list_counter")
        index_summary(deck)
        self.assertFalse(counter.exists())
        deck.load_items()
        index_summary(deck)
        self.assertEqual(counter.read_text(encoding="utf-8").strip(), "1")

    def test_media_bytes_receives_row(self):
        row_path = self.tmp / "media.json"
        os.environ["MEDIA_ROW_PATH"] = str(row_path)
        deck = self._deck("media_row")
        items, _w = deck.load_items()
        plugin = deck.plugin
        assert isinstance(plugin, SwipePlugin)
        plugin.media_bytes("pic", item=items[0].plugin_row, index=0)
        data = json.loads(row_path.read_text(encoding="utf-8"))
        self.assertEqual(data["row"].get("fields", {}).get("colour"), "blue")

    def test_plugin_decided_hidden(self):
        deck = self._deck("decided_flag")
        snap = progress(deck, pending=True)
        ids = [row["id"] for row in snap["items"]]
        self.assertEqual(ids, ["open"])
        self.assertEqual(snap["left"], 1)

    def test_handle_error_not_logged(self):
        deck = self._deck("handle_error")
        deck.load_items()
        result = decide(deck, "x", "right", "")
        self.assertFalse(result["ok"])
        self.assertIn("plugin says no", result["message"])
        self.assertEqual(_read_log(deck), [])

    def test_run_action(self):
        counter = self.tmp / "actions.txt"
        os.environ["ACTION_COUNTER_PATH"] = str(counter)
        deck = self._deck("actions")
        meta = deck.public_meta()
        self.assertTrue(any(a["id"] == "load_more" for a in meta.get("actions") or []))
        out = run_plugin_action(deck, "load_more")
        self.assertTrue(out["ok"])
        self.assertEqual(counter.read_text(encoding="utf-8").strip(), "1")

    def test_private_feed_api(self):
        from choice.httpd import _rows
        from choice.load import Deck, Direction

        public = Deck(
            id="pub",
            title="Pub",
            root=self.tmp,
            state_dir=self.tmp / "s",
            directions={"right": Direction("right", "Y", "y")},
            buttons=[],
            blind=False,
            warnings=[],
            _load=lambda: ([], []),
            private_feed=False,
        )
        private = Deck(
            id="priv",
            title="Priv",
            root=self.tmp,
            state_dir=self.tmp / "p",
            directions={"right": Direction("right", "Y", "y")},
            buttons=[],
            blind=False,
            warnings=[],
            _load=lambda: ([], []),
            private_feed=True,
        )
        rows = _rows([public, private], {})
        self.assertEqual(len(rows), 2)
        priv_row = next(r for r in rows if r["id"] == "priv")
        self.assertTrue(priv_row.get("private"))

    def test_gallery_item_shape(self):
        deck = self._deck("gallery")
        items, _w = deck.load_items()
        self.assertEqual(items[0].kind, "gallery")
        self.assertEqual(len(items[0].images), 2)
        pub = items[0].public(None)
        self.assertEqual(len(pub.get("images") or []), 2)

    def test_string_image_paths(self):
        deck_dir = FIX / "string_images"
        png = deck_dir / "good.png"
        if not png.is_file():
            png.write_bytes(
                bytes.fromhex(
                    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
                    "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
                )
            )
        deck = self._deck("string_images")
        items, warnings = deck.load_items()
        self.assertEqual(len(items[0].images), 1)
        self.assertTrue(items[0].path and items[0].path.is_file())
        self.assertTrue(any("missing.png" in w for w in warnings))
        self.assertTrue(any("not a path or object" in w for w in warnings))
        from choice.httpd import _media_source

        self.assertEqual(_media_source(items[0], "", 0), items[0].path)

    def test_clear_index_on_bust(self):
        from choice.deck_cache import bust
        from choice.deck_index import persisted_summary, snapshot

        deck = self._deck("list_counter")
        deck.load_items()
        self.assertIsNotNone(snapshot(deck))
        bust(deck)
        clear_index(deck)
        self.assertIsNone(snapshot(deck))
        self.assertIsNotNone(persisted_summary(deck))


if __name__ == "__main__":
    unittest.main()
