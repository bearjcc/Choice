# SPDX-License-Identifier: AGPL-3.0-only

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from choice.act import decide, progress, undo
from choice.folder_index import load_index, scan_incremental, wait_folder_index_idle
from choice.load import resolve
from choice.view_prefs import ViewPrefs, save_view_prefs
from choice.work_queue import wait_idle


class UndoPilePositionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.tmp = Path(self._tmp.name)
        self._prev_sync = os.environ.get("CHOICE_SYNC_WORK")
        os.environ["CHOICE_SYNC_WORK"] = "1"

    def tearDown(self):
        if self._prev_sync is None:
            os.environ.pop("CHOICE_SYNC_WORK", None)
        else:
            os.environ["CHOICE_SYNC_WORK"] = self._prev_sync
        for queue in self.tmp.rglob("work_queue.json"):
            wait_idle(queue.parent, timeout=90.0)
        if (self.tmp / "deck.json").is_file():
            try:
                deck = resolve(self.tmp).decks[0]
                wait_folder_index_idle(deck, timeout=90.0)
                wait_idle(deck.state_dir, timeout=90.0)
            except Exception:
                pass
        time.sleep(0.75 if os.name == "nt" else 0.25)
        try:
            self._tmp.cleanup()
        except OSError:
            time.sleep(1.0)
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
        if os.environ.get("CHOICE_SYNC_WORK"):
            self.assertTrue(wait_idle(deck.state_dir, timeout=30.0))
            snap = progress(deck, pending=True, limit=50, offset=0)
            idx = load_index(deck.state_dir)
        else:
            snap = None
            for _ in range(600):
                snap = progress(deck, pending=True, limit=50, offset=0)
                if snap.get("items") and snap["items"][0]["id"] == item_id:
                    break
                time.sleep(0.02)
            idx = None
            for _ in range(600):
                idx = load_index(deck.state_dir)
                if idx.ordered and idx.ordered[0] == item_id:
                    break
                time.sleep(0.02)
        self.assertTrue(snap and snap.get("items"), snap)
        self.assertEqual(snap["items"][0]["id"], item_id)
        self.assertEqual(idx.ordered[0], item_id)

    def test_undo_scan_order_while_move_queued(self):
        os.environ.pop("CHOICE_SYNC_WORK", None)
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
        os.environ.pop("CHOICE_SYNC_WORK", None)
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
