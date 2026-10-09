# SPDX-License-Identifier: AGPL-3.0-only

import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from choice.act import _read_log, decide, progress, undo
from choice.file_moves import move_file
from choice.folder_index import load_index, scan_incremental
from choice.load import resolve
from choice.view_prefs import ViewPrefs, save_view_prefs
from choice.work_queue import boot_deck, wait_idle


class UndoRunningMoveTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._sync = os.environ.pop("CHOICE_SYNC_WORK", None)

    def tearDown(self):
        if self._sync is not None:
            os.environ["CHOICE_SYNC_WORK"] = self._sync
        self._tmp.cleanup()

    def _deck(self, *, random_sort: bool = False):
        for name in ("keep", "love"):
            (self.tmp / name).mkdir()
        pile = self.tmp / "pile"
        pile.mkdir()
        (pile / "locked.jpg").write_bytes(b"x")
        (self.tmp / "deck.json").write_text(
            json.dumps(
                {
                    "source": {
                        "type": "images",
                        "path": ".",
                        "recursive": True,
                        "output": "sort",
                        "sort": {"right": "keep", "down": "love"},
                    },
                    "directions": {
                        "right": {"label": "Keep", "value": "keep"},
                        "down": {"label": "Love", "value": "love"},
                    },
                }
            ),
            encoding="utf-8",
        )
        deck = resolve(self.tmp).decks[0]
        scan_incremental(deck)
        if random_sort:
            save_view_prefs(deck, ViewPrefs(sort_mode="random", random_seed="undo-run"))
        return deck

    def _run_case(self, random_sort: bool) -> None:
        os.environ.pop("CHOICE_SYNC_WORK", None)
        deck = self._deck(random_sort=random_sort)
        rel = "pile/locked.jpg"
        gate = threading.Event()
        real_move = move_file

        def gated_move(src: Path, dest: Path) -> None:
            if src.name == "locked.jpg":
                gate.wait(timeout=30.0)
            real_move(src, dest)

        boot_deck(deck)
        with patch("choice.file_moves.move_file", side_effect=gated_move):
            decide(deck, rel, "down", None)
            time.sleep(0.5)
            undo(deck)
            gate.set()
        wait_idle(deck.state_dir, timeout=60.0)
        self.assertTrue((self.tmp / rel).is_file())
        self.assertFalse((self.tmp / "love" / "locked.jpg").is_file())
        snap = progress(deck, pending=True, limit=5, after=None)
        self.assertEqual(snap["items"][0]["id"], rel)
        idx = load_index(deck.state_dir)
        self.assertEqual(idx.ordered[0], rel)
        undone = {r.get("ref") for r in _read_log(deck) if r.get("type") == "undo"}
        active = [
            r
            for r in _read_log(deck)
            if r.get("type") == "decision" and r.get("id") not in undone
        ]
        self.assertFalse(any(r.get("item") == rel for r in active))

    def test_undo_while_move_running_scan_order(self):
        self._run_case(False)

    def test_undo_while_move_running_random_order(self):
        self._run_case(True)


if __name__ == "__main__":
    unittest.main()
