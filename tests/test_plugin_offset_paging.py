# SPDX-License-Identifier: AGPL-3.0-only

import os
import tempfile
import unittest
from pathlib import Path

from choice.act import progress
from choice.open import open_config

FIX = Path(__file__).resolve().parent / "fixtures" / "plugin_host"


class PluginOffsetPagingTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        os.environ["CHOICE_DISABLE_WARM"] = "1"

    def tearDown(self):
        os.environ.pop("CHOICE_DISABLE_WARM", None)
        self._tmp.cleanup()

    def _deck(self):
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
mount = "big_list"
""".strip(),
            encoding="utf-8",
        )
        return open_config(cfg).decks[0]

    def test_offset_reaches_past_first_page(self):
        deck = self._deck()
        deck.load_items()
        first = progress(deck, pending=True, limit=200, offset=0)
        second = progress(deck, pending=True, limit=200, offset=200)
        self.assertEqual(first.get("left"), 500)
        self.assertEqual(len(first["items"]), 200)
        self.assertEqual(second.get("next_offset"), 400)
        self.assertGreater(len(second["items"]), 0)
        self.assertEqual(second["items"][0]["id"], "item-0200")
