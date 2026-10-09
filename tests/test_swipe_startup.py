# SPDX-License-Identifier: AGPL-3.0-only

import os
import tempfile
import unittest
from pathlib import Path

from choice.open import open_config

FIX = Path(__file__).resolve().parent / "fixtures" / "plugin_host"


class SwipeStartupTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        os.environ["CHOICE_DISABLE_WARM"] = "1"

    def tearDown(self):
        os.environ.pop("CHOICE_DISABLE_WARM", None)
        self._tmp.cleanup()

    def _write_config(self, body: str) -> Path:
        cfg = self.tmp / "choice.toml"
        cfg.write_text(body.strip() + "\n", encoding="utf-8")
        return cfg

    def test_plugin_deck_with_directions_in_options_loads(self):
        cfg = self._write_config(
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
mount = "list_counter"
directions = {{ left = {{ label = "Nope", value = "no" }}, right = {{ label = "Yep", value = "yes" }} }}
"""
        )
        opened = open_config(cfg)
        self.assertEqual(len(opened.decks), 1)
        deck = opened.decks[0]
        self.assertIsNone(deck.problem)
        self.assertEqual(deck.directions["left"].label, "Nope")
        self.assertEqual(deck.directions["right"].label, "Yep")

    def test_broken_deck_does_not_block_others(self):
        cfg = self._write_config(
            f"""
[state]
dir = "state"

[[sources]]
id = "swipe"
type = "swipe"
path = "{FIX.as_posix()}"

[[decks]]
id = "good"
title = "Good"
source = "swipe"
mount = "list_counter"

[[decks]]
id = "bad"
title = "Bad"
source = "swipe"
mount = "broken_boot"
"""
        )
        opened = open_config(cfg)
        self.assertEqual(len(opened.decks), 2)
        by_id = {d.id: d for d in opened.decks}
        self.assertIsNone(by_id["good"].problem)
        self.assertIsNotNone(by_id["bad"].problem)
        self.assertIn("broken", by_id["bad"].problem.lower())
