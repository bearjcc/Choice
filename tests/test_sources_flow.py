# SPDX-License-Identifier: AGPL-3.0-only

import os
import tempfile
import unittest
from pathlib import Path

from choice.act import decide, progress, view
from choice.config import load_config, write_secret
from choice.flow import arrange
from choice.load import resolve
from choice.open import open_config
from choice.rated import update

ROOT = Path(__file__).resolve().parents[1]
SWIPE = ROOT / "tests" / "fixtures" / "swipe" / "example_images"


class SourceFlowTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_swipe_plugin_deck_loads(self):
        if not (SWIPE / "deck.py").is_file():
            self.skipTest("swipe fixture missing")
        cfg_path = self.tmp / "choice.toml"
        cfg_path.write_text(
            f"""
[state]
dir = "state"

[[sources]]
id = "swipe"
type = "swipe"
path = "{SWIPE.parent.as_posix()}"

[[decks]]
id = "example_images"
title = "Example images"
source = "swipe"
mount = "example_images"
""",
            encoding="utf-8",
        )
        opened = open_config(cfg_path)
        deck = next(d for d in opened.decks if d.id == "example_images")
        self.assertIsNone(deck.problem)
        items, warnings = deck.load_items()
        self.assertGreater(len(items), 0)
        self.assertEqual(warnings, [])

    def test_taste_filters_then_pairs(self):
        deck = next(d for d in resolve(ROOT / "examples").decks if d.id == "taste")
        for row in deck.load_items()[0]:
            decide(deck, row.id, "right" if row.id != "b3" else "left", None)
        flow = view(deck)
        self.assertTrue(flow.items)
        self.assertIn(flow.items[0].kind, {"pair", "card"})

    def test_rated_deck_progress_label(self):
        deck = next(d for d in resolve(ROOT / "examples").decks if d.id == "rated")
        items, _w = deck.load_items()
        flow = arrange(deck, items, {})
        self.assertEqual(flow.items[0].kind, "pair")
        snap = progress(deck, pending=True)
        self.assertIn("Rated", snap.get("count_label") or "")

    def test_rated_pair_update(self):
        from choice.rated import Player

        players = {"a": Player("a"), "b": Player("b")}
        update(players, "a", "b")
        self.assertGreater(players["a"].rating, 1500.0)

    def test_secret_write_masks_in_config_api(self):
        cfg_path = self.tmp / "choice.toml"
        cfg_path.write_text(
            """
[state]
dir = "state"

[[sources]]
id = "x"
type = "folder"
path = "."

[[decks]]
id = "d"
title = "D"
source = "x"
mount = "."
""",
            encoding="utf-8",
        )
        cfg = load_config(cfg_path)
        write_secret(cfg, "IMMICH_API_KEY", "test-key-value")
        os.environ["IMMICH_API_KEY"] = "from-env"
        from choice.config import resolve_secret

        self.assertEqual(resolve_secret("IMMICH_API_KEY", cfg), "from-env")

    def test_export_shape(self):
        deck = next(d for d in resolve(ROOT / "examples" / "yes-no").decks if True)
        decide(deck, "1", "right", None)
        from choice.act import _read_log

        rows = _read_log(deck)
        self.assertTrue(any(r.get("type") == "decision" for r in rows))


if __name__ == "__main__":
    unittest.main()
