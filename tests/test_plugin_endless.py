# SPDX-License-Identifier: AGPL-3.0-only

import os
import tempfile
import unittest
from pathlib import Path

from choice.act import index_summary, progress
from choice.count_prefs import auto_hide_counts, counts_hidden
from choice.open import open_config

FIX = Path(__file__).resolve().parent / "fixtures" / "plugin_host"


class PluginEndlessTests(unittest.TestCase):
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

    def test_endless_only_shows_infinity(self):
        deck = self._deck("endless_plain")
        deck.load_items()
        home = index_summary(deck)
        items = progress(deck, pending=True, limit=10)
        self.assertTrue(home.get("endless"))
        self.assertEqual(home.get("count_label"), "∞")
        self.assertIsNone(home.get("left"))
        self.assertIsNone(home.get("total"))
        self.assertFalse(home.get("meter"))
        self.assertTrue(items.get("endless"))
        self.assertEqual(items.get("count_label"), "∞")
        self.assertTrue(auto_hide_counts(deck))
        self.assertTrue(counts_hidden(deck))

    def test_endless_with_custom_label(self):
        deck = self._deck("endless_label")
        deck.load_items()
        label = "∞ · 62% unsettled"
        home = index_summary(deck)
        items = progress(deck, pending=True, limit=10)
        self.assertTrue(home.get("endless"))
        self.assertEqual(home.get("count_label"), label)
        self.assertEqual(items.get("count_label"), label)

    def test_plain_plugin_unchanged(self):
        deck = self._deck("list_counter")
        deck.load_items()
        home = index_summary(deck)
        items = progress(deck, pending=True, limit=10)
        self.assertNotIn("endless", home)
        self.assertEqual(home["left"], 1)
        self.assertEqual(home["total"], 1)
        self.assertNotIn("endless", items)
        self.assertEqual(items["left"], 1)

    def test_label_without_endless_keeps_meter_and_total(self):
        deck = self._deck("labeled_not_endless")
        deck.load_items()
        home = index_summary(deck)
        items = progress(deck, pending=True, limit=10)
        self.assertNotIn("endless", home)
        self.assertNotIn("endless", items)
        self.assertEqual(home["left"], 3)
        self.assertEqual(home["total"], 3)
        self.assertEqual(home.get("count_label"), "2 borderline left")
        self.assertTrue(home.get("meter"))
        self.assertEqual(items.get("count_label"), "2 borderline left")
        self.assertEqual(items["left"], 3)

    def test_swipe_deck_stats_endless_passthrough(self):
        deck = self._deck("stats_swipe")
        deck.load_items()
        from choice.plugin_stats import plugin_stats_raw

        self.assertTrue(plugin_stats_raw(deck).get("endless"))
        self.assertEqual(plugin_stats_raw(deck).get("count_label"), "from stats()")
        home = index_summary(deck)
        self.assertTrue(home.get("endless"))
        self.assertEqual(home.get("count_label"), "from stats()")


if __name__ == "__main__":
    unittest.main()
