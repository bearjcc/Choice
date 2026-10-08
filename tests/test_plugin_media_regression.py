# SPDX-License-Identifier: AGPL-3.0-only

import os
import tempfile
import unittest
from pathlib import Path

from choice.open import open_config
from choice.swipe_plugin import SwipePlugin

FIX = Path(__file__).resolve().parent / "fixtures" / "plugin_host"
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


class PluginMediaRegressionTests(unittest.TestCase):
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

    def _deck(self, mount: str):
        return open_config(self._config(mount)).decks[0]

    def _assert_renders_media(self, deck, item_id: str):
        items, _warnings = deck.load_items()
        item = next(i for i in items if i.id == item_id)
        pub = item.public(None)
        self.assertTrue(pub.get("media"), msg=f"{item_id} should expose media")
        plugin = deck.plugin
        assert isinstance(plugin, SwipePlugin)
        blob = plugin.media_bytes(item.id, item=item.plugin_row, index=0)
        if blob is None and item.path and item.path.is_file():
            self.assertTrue(item.path.is_file())
            return
        self.assertIsNotNone(blob, msg=f"{item_id} should serve bytes or a local file")

    def test_relative_string_images(self):
        folder = FIX / "string_images"
        (folder / "good.png").write_bytes(PNG)
        deck = self._deck("string_images")
        items, warnings = deck.load_items()
        item = next(i for i in items if i.id == "listing")
        self.assertTrue(item.public(None).get("media"))
        self.assertTrue(item.path and item.path.is_file())
        self.assertTrue(any("missing.png" in w for w in warnings))

    def test_absolute_path_outside_deck(self):
        outside = self.tmp / "shared_cache" / "photo.png"
        outside.parent.mkdir(parents=True)
        outside.write_bytes(PNG)
        os.environ["MEDIA_ABSOLUTE_PATH"] = str(outside)
        try:
            deck = self._deck("media_absolute")
            items, warnings = deck.load_items()
            item = next(i for i in items if i.id == "cached")
            self.assertFalse(any("outside deck" in w for w in warnings))
            self.assertTrue(item.public(None).get("media"))
            self.assertEqual(item.path.resolve(), outside.resolve())
        finally:
            os.environ.pop("MEDIA_ABSOLUTE_PATH", None)

    def test_plugin_token_media_bytes(self):
        deck = self._deck("media_token")
        self._assert_renders_media(deck, "asset")

    def test_dict_image_entries(self):
        deck = self._deck("gallery")
        self._assert_renders_media(deck, "listing")

    def test_index_uses_persisted_counts(self):
        from choice.act import index_summary
        from choice.deck_index import record_items

        deck = self._deck("gallery")
        items, _w = deck.load_items()
        record_items(deck, items)
        snap = index_summary(deck)
        self.assertEqual(snap["total"], len(items))
        fresh = open_config(self._config("gallery")).decks[0]
        cached = index_summary(fresh)
        self.assertEqual(cached["total"], len(items))
        self.assertTrue(cached.get("meter"))
