# SPDX-License-Identifier: AGPL-3.0-only

import json
import tempfile
import unittest
from pathlib import Path

from choice.act import (
    DecideTestAbort,
    _read_log,
    decide,
    set_decide_test_hook,
)
from choice.folder_index import load_index, scan_incremental
from choice.load import resolve
from choice.work_queue import boot_deck, enqueue_planned_op, wait_idle


class DecideLogOrderTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        set_decide_test_hook(None)
        self._tmp.cleanup()

    def _sort_deck(self, n_files: int = 5):
        for name in ("keep", "reject"):
            (self.tmp / name).mkdir(exist_ok=True)
        pile = self.tmp / "pile"
        pile.mkdir()
        for i in range(n_files):
            (pile / f"f{i:03d}.jpg").write_bytes(b"x")
        (self.tmp / "deck.json").write_text(
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
        deck = resolve(self.tmp).decks[0]
        scan_incremental(deck)
        return deck

    def test_abort_after_log_leaves_consistent_pile_on_boot(self):
        deck = self._sort_deck()
        target = load_index(deck.state_dir).ordered[0]
        set_decide_test_hook("after_log")
        with self.assertRaises(DecideTestAbort):
            decide(deck, target, "right", None)
        set_decide_test_hook(None)
        self.assertEqual(len(_read_log(deck)), 1)
        boot_deck(deck)
        self.assertTrue(wait_idle(deck.state_dir, timeout=30.0))
        idx = load_index(deck.state_dir)
        self.assertEqual(len(idx.ordered), 4)
        self.assertNotIn(target, idx.ordered)
        self.assertTrue((self.tmp / "keep" / Path(target).name).is_file())

    def test_orphan_job_without_decision_is_reversed_on_boot(self):
        deck = self._sort_deck()
        idx = load_index(deck.state_dir)
        self.assertEqual(len(idx.ordered), 5)
        target = idx.ordered[0]
        from choice.folder_index import apply_move

        apply_move(deck.state_dir, target, "keep/" + Path(target).name, deck=deck)
        enqueue_planned_op(
            deck,
            "orphan-decision",
            {"op": "move", "from": target, "to": "keep/" + Path(target).name},
        )
        self.assertEqual(len(load_index(deck.state_dir).ordered), 4)
        boot_deck(deck)
        self.assertEqual(len(load_index(deck.state_dir).ordered), 5)
        self.assertIn(target, load_index(deck.state_dir).ordered)
