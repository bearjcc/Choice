# SPDX-License-Identifier: AGPL-3.0-only

import json
import tempfile
import unittest
from pathlib import Path

from choice.act import progress
from choice.open import resolve


class ExternalLogAppendTests(unittest.TestCase):
    def test_progress_sees_appended_decision(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "items.jsonl").write_text(
            '{"id":"a","title":"A"}\n{"id":"b","title":"B"}\n',
            encoding="utf-8",
        )
        (tmp / "deck.json").write_text(
            json.dumps(
                {
                    "source": {"type": "jsonl", "path": "items.jsonl"},
                    "show": {"title": "{{title}}"},
                    "directions": {
                        "right": {"label": "Yes", "value": "yes"},
                        "left": {"label": "No", "value": "no"},
                    },
                }
            ),
            encoding="utf-8",
        )
        deck = resolve(tmp).decks[0]
        deck.state_dir.mkdir(parents=True, exist_ok=True)
        before = progress(deck, pending=True)
        self.assertEqual(before["left"], 2)
        log = deck.state_dir / "decisions.jsonl"
        log.write_text(
            json.dumps(
                {
                    "type": "decision",
                    "id": "ext-1",
                    "item": "a",
                    "direction": "right",
                    "value": "yes",
                    "label": "Yes",
                    "later": False,
                    "note": "",
                    "ts": "2026-01-01T00:00:00",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        after = progress(deck, pending=True)
        self.assertEqual(after["left"], 1)
        self.assertEqual(after["decided"], 1)
