# SPDX-License-Identifier: AGPL-3.0-only

import os
import tempfile
import unittest
from pathlib import Path

from choice.deck_index import clear_index, record_items, snapshot
from choice.open import open_config
from choice.sources.swipe import SwipeSource

FIX = Path(__file__).resolve().parent / "fixtures" / "plugin_host"


class PluginLoadResilienceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
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

    def test_partial_list_then_snapshot_on_throw(self):
        opened = open_config(self._config("chaotic_list"))
        deck = opened.decks[0]
        clear_index(deck)
        deck.plugin.obj._mode = "throw"
        items, warnings = deck.load_items()
        self.assertEqual([i.id for i in items], ["good-1", "good-2"])
        self.assertTrue(any("skipped" in w for w in warnings))
        snap = snapshot(deck)
        self.assertIsNotNone(snap)
        self.assertEqual(len(snap.ids), 2)

        deck.plugin.obj._mode = "raise"
        items2, warnings2 = deck.load_items()
        self.assertEqual([i.id for i in items2], ["good-1", "good-2"])
        self.assertTrue(any("last good" in w.lower() for w in warnings2))

    def test_mutating_list_still_loads(self):
        opened = open_config(self._config("chaotic_list"))
        deck = opened.decks[0]
        clear_index(deck)
        deck.plugin.obj._mode = "mutate"
        items, _warnings = deck.load_items()
        self.assertEqual(len(items), 3)
        self.assertEqual({i.id for i in items}, {"m-1", "m-2", "m-3"})

    def test_cached_load_uses_snapshot_after_failure(self):
        opened = open_config(self._config("chaotic_list"))
        deck = opened.decks[0]
        clear_index(deck)
        from choice.load import Item

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
        deck.plugin.obj._mode = "raise"
        from choice.deck_cache import load_items as cached_load

        items, warnings = cached_load(deck)
        self.assertTrue(items)
        self.assertEqual(items[0].id, "cached")
        self.assertTrue(warnings)


if __name__ == "__main__":
    unittest.main()
