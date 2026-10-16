# SPDX-License-Identifier: AGPL-3.0-only

import os
import tempfile
import unittest
from pathlib import Path

from choice.open import open_config
from choice.swipe_plugin import SwipePlugin, load_swipe_class, swipe_item_to_choice

FIX = Path(__file__).resolve().parent / "fixtures" / "plugin_host"


class SwipeAbSectionsTests(unittest.TestCase):
    def test_ab_text_alias_and_sections(self):
        folder = FIX / "gallery"
        plugin = SwipePlugin(
            obj=load_swipe_class(folder / "deck.py", folder.name),
            folder=folder,
            deck_id="t",
            title="T",
        )
        row = {
            "id": "pair-1",
            "title": "Pick one",
            "body": "ignored on pair",
            "sections": [{"title": "Context", "text": "Shared notes", "main": True}],
            "ab": {
                "a": {"label": "A", "text": "Alpha text"},
                "b": {"label": "B", "text": "Beta text"},
            },
        }
        item, notes = swipe_item_to_choice(row, folder, plugin)
        self.assertEqual(item.kind, "pair")
        self.assertEqual(item.sides[0].body, "Alpha text")
        self.assertEqual(item.sides[1].body, "Beta text")
        self.assertEqual(len(item.sections), 1)
        self.assertEqual(item.sections[0]["text"], "Shared notes")

    def test_pair_fixture_loads(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "choice.toml"
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
mount = "pair_audit"
""".strip(),
                encoding="utf-8",
            )
            os.environ["CHOICE_DISABLE_WARM"] = "1"
            try:
                deck = open_config(cfg).decks[0]
                items, _ = deck.load_items()
                self.assertTrue(items)
                pub = items[0].public(None)
                self.assertIn("sections", pub)
                self.assertIn("sides", pub)
            finally:
                os.environ.pop("CHOICE_DISABLE_WARM", None)


if __name__ == "__main__":
    unittest.main()
