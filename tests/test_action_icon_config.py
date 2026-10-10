# SPDX-License-Identifier: AGPL-3.0-only

import json
import tempfile
import unittest
from pathlib import Path

from choice.folder_deck import apply_sort_direction_labels
from choice.load import Direction, _one_direction


class ActionIconConfigTests(unittest.TestCase):
    def test_unknown_direction_icon_does_not_break_deck(self):
        d = _one_direction("right", {"label": "Yes", "icon": "not-a-real-icon"})
        self.assertIsNone(d.icon)
        self.assertEqual(d.label, "Yes")

    def test_sort_icon_without_label_does_not_add_direction(self):
        base = {
            "left": Direction(id="left", label="No", value="no"),
            "right": Direction(id="right", label="Yes", value="yes"),
        }
        merged = apply_sort_direction_labels(
            base,
            {"sort_up_icon": "star"},
        )
        self.assertNotIn("up", merged)
        self.assertEqual(merged["right"].label, "Yes")

    def test_sort_icon_applies_to_existing_direction(self):
        base = {
            "left": Direction(id="left", label="No", value="no"),
            "right": Direction(id="right", label="Yes", value="yes"),
        }
        merged = apply_sort_direction_labels(
            base,
            {"sort_right_icon": "heart"},
        )
        self.assertEqual(merged["right"].icon, "heart")


class UnknownIconDeckJsonTests(unittest.TestCase):
    def test_deck_json_unknown_icon_still_loads(self):
        from choice.load import resolve

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "items.jsonl").write_text('{"id":"a","title":"A"}\n', encoding="utf-8")
            deck_json = {
                "title": "T",
                "directions": {
                    "right": {"label": "Yes", "icon": "bogus"},
                },
            }
            (root / "deck.json").write_text(json.dumps(deck_json), encoding="utf-8")
            deck = resolve(root).decks[0]
            self.assertIsNone(deck.problem)
            self.assertIsNone(deck.directions["right"].icon)


if __name__ == "__main__":
    unittest.main()
