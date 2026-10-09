# SPDX-License-Identifier: AGPL-3.0-only

import json
import tempfile
import unittest
from pathlib import Path

from choice.act import decide, index_summary
from choice.folder_index import load_index, scan_incremental
from choice.load import resolve


class FolderSortIndexTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _sort_deck(self, extra_sort: dict | None = None):
        sort = {"right": "keep", "left": "reject", "up": "like", "down": "love"}
        if extra_sort:
            sort.update(extra_sort)
        (self.tmp / "deck.json").write_text(
            json.dumps(
                {
                    "source": {
                        "type": "images",
                        "path": ".",
                        "recursive": True,
                        "output": "sort",
                        "sort": sort,
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
        for name in ("keep", "reject", "like", "love", "dislike"):
            (self.tmp / name).mkdir(exist_ok=True)
        (self.tmp / "incoming").mkdir(exist_ok=True)
        (self.tmp / "incoming" / "a.jpg").write_bytes(b"x")
        (self.tmp / "reject" / "old.jpg").write_bytes(b"x")
        deck = resolve(self.tmp).decks[0]
        scan_incremental(deck)
        return deck

    def test_sort_folders_excluded_from_index(self):
        deck = self._sort_deck()
        idx = load_index(deck.state_dir)
        self.assertEqual(idx.ordered, ["incoming/a.jpg"])
        self.assertNotIn("reject/old.jpg", idx.ordered)

    def test_move_removes_from_index_not_relisted_at_dest(self):
        deck = self._sort_deck()
        decide(deck, "incoming/a.jpg", "right", None)
        idx = load_index(deck.state_dir)
        self.assertEqual(idx.ordered, [])
        scan_incremental(deck)
        idx = load_index(deck.state_dir)
        self.assertEqual(idx.ordered, [])
        self.assertTrue((self.tmp / "keep" / "a.jpg").is_file())

    def test_already_decided_does_not_move_again(self):
        deck = self._sort_deck()
        (self.tmp / "incoming" / "b.jpg").write_bytes(b"y")
        scan_incremental(deck)
        decide(deck, "incoming/b.jpg", "left", None)
        self.assertTrue((self.tmp / "reject" / "b.jpg").is_file())
        again = decide(deck, "incoming/b.jpg", "right", None)
        self.assertFalse(again["ok"])
        self.assertFalse((self.tmp / "keep" / "b.jpg").is_file())

    def test_counts_exclude_sorted_pile(self):
        deck = self._sort_deck()
        for i in range(5):
            (self.tmp / "incoming" / f"f{i}.jpg").write_bytes(b"x")
        (self.tmp / "incoming").touch()
        scan_incremental(deck)
        snap = index_summary(deck)
        self.assertEqual(snap.get("left"), 6)
