# SPDX-License-Identifier: AGPL-3.0-only

import json
import tempfile
import unittest
from pathlib import Path

from choice.act import decide, progress
from choice.folder_index import scan_incremental
from choice.load import resolve


class FolderProgressDecidedTests(unittest.TestCase):
    def test_sort_deck_progress_uses_log_decided(self):
        with tempfile.TemporaryDirectory() as tmpname:
            tmp = Path(tmpname)
            (tmp / "deck.json").write_text(
                json.dumps(
                    {
                        "source": {
                            "type": "images",
                            "path": ".",
                            "recursive": True,
                            "output": "sort",
                            "sort": {"right": "keep", "left": "reject"},
                        },
                        "directions": {
                            "right": {"label": "Keep", "value": "keep"},
                            "left": {"label": "Reject", "value": "reject"},
                        },
                    }
                ),
                encoding="utf-8",
            )
            for name in ("keep", "reject", "incoming"):
                (tmp / name).mkdir()
            (tmp / "incoming" / "a.jpg").write_bytes(b"x")
            (tmp / "incoming" / "b.jpg").write_bytes(b"y")
            deck = resolve(tmp).decks[0]
            scan_incremental(deck)
            decide(deck, "incoming/a.jpg", "right", None)
            scan_incremental(deck)
            snap = progress(deck, pending=True, limit=200)
            self.assertTrue(snap.get("ok"))
            self.assertGreater(snap["decided"], 0)
            self.assertEqual(snap["total"], snap["decided"] + snap["left"])
