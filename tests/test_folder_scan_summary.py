# SPDX-License-Identifier: AGPL-3.0-only

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from choice.act import decide, index_summary
from choice.folder_index import (
    FolderIndex,
    _tree_dirs_changed,
    load_index,
    save_index,
    scan_incremental,
    summary,
)
from choice.load import resolve


class FolderScanSummaryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        os.environ["CHOICE_DISABLE_WARM"] = "1"

    def tearDown(self):
        os.environ.pop("CHOICE_DISABLE_WARM", None)
        try:
            self._tmp.cleanup()
        except OSError:
            time.sleep(0.5)
            self._tmp.cleanup()

    def _sort_deck(self):
        (self.tmp / "deck.json").write_text(
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
                            "up": "like",
                            "down": "love",
                        },
                    },
                    "directions": {
                        "right": {"label": "Keep", "value": "keep"},
                        "left": {"label": "Reject", "value": "reject"},
                        "up": {"label": "Like", "value": "like"},
                        "down": {"label": "Love", "value": "love"},
                    },
                }
            ),
            encoding="utf-8",
        )
        for name in ("keep", "reject", "like", "love", "incoming"):
            (self.tmp / name).mkdir(exist_ok=True)
        (self.tmp / "incoming" / "a.jpg").write_bytes(b"x")
        (self.tmp / "incoming" / "b.jpg").write_bytes(b"y")
        deck = resolve(self.tmp).decks[0]
        scan_incremental(deck)
        return deck

    def test_save_index_creates_state_dir_when_missing(self):
        deck = self._sort_deck()
        fresh = self.tmp / "other-state"
        self.assertFalse(fresh.is_dir())
        save_index(fresh, FolderIndex(ordered=["x.jpg"]))
        self.assertTrue((fresh / "folder_index.json").is_file())

    def test_decide_does_not_mark_tree_outdated_or_schedule_scan(self):
        deck = self._sort_deck()
        from choice.work_queue import wait_idle

        wait_idle(deck.state_dir, timeout=30.0)
        with patch("choice.folder_index.schedule_scan") as scheduled:
            decide(deck, "incoming/a.jpg", "right", None)
        scheduled.assert_not_called()
        wait_idle(deck.state_dir, timeout=30.0)
        idx = load_index(deck.state_dir)
        self.assertFalse(_tree_dirs_changed(deck, idx))

    def test_summary_keeps_totals_while_scanning(self):
        deck = self._sort_deck()
        idx = load_index(deck.state_dir)
        idx.scanning = True
        save = __import__("choice.folder_index", fromlist=["save_index"]).save_index
        save(deck.state_dir, idx)
        snap = summary(deck, set())
        self.assertEqual(snap.get("total"), 2)
        self.assertEqual(snap.get("left"), 2)
        self.assertTrue(snap.get("meter"))
        self.assertIn("scanning", snap.get("count_label") or "")
        home = index_summary(deck)
        self.assertEqual(home.get("left"), 2)
        self.assertIsNotNone(home.get("total"))
