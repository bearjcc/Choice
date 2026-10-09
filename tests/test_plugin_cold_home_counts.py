# SPDX-License-Identifier: AGPL-3.0-only

import json
import os
import tempfile
import unittest
from pathlib import Path

from choice.act import index_summary, progress
from choice.deck_index import clear_index
from choice.open import open_config

FIX = Path(__file__).resolve().parent / "fixtures" / "plugin_host"


class PluginColdHomeCountsTests(unittest.TestCase):
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

    def test_home_matches_items_with_stale_list_counts(self):
        deck = open_config(self._config("big_list")).decks[0]
        deck.load_items()
        counts = deck.state_dir / "list_counts.json"
        stale = {
            "total": 3,
            "plugin_decided": [],
            "ids": ["item-0000", "item-0001", "item-0002"],
            "order": ["item-0000", "item-0001", "item-0002"],
        }
        counts.write_text(json.dumps(stale), encoding="utf-8")
        clear_index(deck)
        home = index_summary(deck)
        items = progress(deck, pending=True, limit=50)
        self.assertIsNotNone(home.get("total"))
        self.assertIsNotNone(home.get("left"))
        self.assertEqual(home["total"], items["total"])
        self.assertEqual(home["left"], items["left"])
        self.assertEqual(home["left"], 500)

    def test_home_never_none_total_after_hot_reload(self):
        deck = open_config(self._config("hides_decided")).decks[0]
        deck.load_items()
        clear_index(deck)
        home = index_summary(deck)
        self.assertIsNotNone(home.get("total"))
        self.assertIsNotNone(home.get("left"))
