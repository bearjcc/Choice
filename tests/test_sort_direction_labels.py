# SPDX-License-Identifier: AGPL-3.0-only

import json
import tempfile
import unittest
from pathlib import Path

from choice.load import resolve


class SortDirectionLabelTests(unittest.TestCase):
    def test_sort_label_keys_override_defaults(self):
        with tempfile.TemporaryDirectory() as tmpname:
            tmp = Path(tmpname)
            for folder in ("keep", "reject", "equal", "skip"):
                (tmp / folder).mkdir()
            (tmp / "deck.json").write_text(
                json.dumps(
                    {
                        "source": {
                            "type": "images",
                            "path": ".",
                            "recursive": True,
                            "output": "sort",
                            "sort": {
                                "right": "keep",
                                "left": "reject",
                                "up": "equal",
                                "down": "skip",
                            },
                            "sort_left_label": "A",
                            "sort_right_label": "B",
                            "sort_up_label": "Equal",
                            "sort_down_label": "Skip",
                        },
                    }
                ),
                encoding="utf-8",
            )
            deck = resolve(tmp).decks[0]
            self.assertEqual(deck.directions["left"].label, "A")
            self.assertEqual(deck.directions["right"].label, "B")
            self.assertEqual(deck.directions["up"].label, "Equal")
            self.assertEqual(deck.directions["down"].label, "Skip")
            meta = deck.public_meta()
            labels = {row["id"]: row["label"] for row in meta["directions"]}
            self.assertEqual(labels["left"], "A")
            self.assertEqual(labels["right"], "B")
