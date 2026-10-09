# SPDX-License-Identifier: AGPL-3.0-only

import json
import os
import tempfile
import unittest
from pathlib import Path

from choice.act import decide, progress, undo
from choice.folder_index import load_index, scan_incremental
from choice.load import resolve
from choice.view_prefs import ViewPrefs, save_view_prefs
from choice.work_queue import wait_idle


class UndoPilePositionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._sync = os.environ.pop("CHOICE_SYNC_WORK", None)

    def tearDown(self):
        if self._sync is not None:
            os.environ["CHOICE_SYNC_WORK"] = self._sync
        self._tmp.cleanup()

    def _big_sort_deck(self, *, random_sort: bool = False):
        for name in ("keep", "reject", "like", "love"):
            (self.tmp / name).mkdir(exist_ok=True)
        pile = self.tmp / "pile"
        pile.mkdir()
        for i in range(250):
            (pile / f"f{i:03d}.jpg").write_bytes(b"x")
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
        deck = resolve(self.tmp).decks[0]
        scan_incremental(deck)
        if random_sort:
            save_view_prefs(deck, ViewPrefs(sort_mode="random", random_seed="undo-test"))
        return deck

    def _first_pending_id(self, deck):
        snap = progress(deck, pending=True, limit=50, offset=0)
        self.assertTrue(snap["items"])
        return snap["items"][0]["id"]

    def _assert_first_after_undo(self, deck, item_id: str):
        undo(deck)
        snap = progress(deck, pending=True, limit=50, offset=0)
        self.assertTrue(snap["items"], snap)
        self.assertEqual(snap["items"][0]["id"], item_id)
        idx = load_index(deck.state_dir)
        self.assertEqual(idx.ordered[0], item_id)

    def test_undo_scan_order_while_move_queued(self):
        deck = self._big_sort_deck()
        first = self._first_pending_id(deck)
        decide(deck, first, "right", None)
        self._assert_first_after_undo(deck, first)

    def test_undo_scan_order_after_move_finished(self):
        deck = self._big_sort_deck()
        first = self._first_pending_id(deck)
        decide(deck, first, "right", None)
        self.assertTrue(wait_idle(deck.state_dir, timeout=30.0))
        self._assert_first_after_undo(deck, first)

    def test_undo_random_order_while_move_queued(self):
        deck = self._big_sort_deck(random_sort=True)
        first = self._first_pending_id(deck)
        decide(deck, first, "right", None)
        self._assert_first_after_undo(deck, first)

    def test_undo_random_order_after_move_finished(self):
        deck = self._big_sort_deck(random_sort=True)
        first = self._first_pending_id(deck)
        decide(deck, first, "right", None)
        self.assertTrue(wait_idle(deck.state_dir, timeout=30.0))
        self._assert_first_after_undo(deck, first)
