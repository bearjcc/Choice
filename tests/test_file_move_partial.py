# SPDX-License-Identifier: AGPL-3.0-only

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from choice.act import _read_log, decide, index_summary
from choice.file_moves import MoveNotReady, move_file, remove_source
from choice.folder_index import load_index, scan_incremental
from choice.load import resolve
from choice.work_queue import _save_jobs, boot_deck, drop_memory_state, reconcile_deck, wait_idle


def _unsorted_incoming(root: Path) -> int:
    incoming = root / "incoming"
    if not incoming.is_dir():
        return 0
    return sum(1 for p in incoming.iterdir() if p.is_file() and not p.name.startswith("."))


class FileMovePartialTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._sync = os.environ.get("CHOICE_SYNC_WORK")

    def tearDown(self):
        if self._sync is None:
            os.environ.pop("CHOICE_SYNC_WORK", None)
        else:
            os.environ["CHOICE_SYNC_WORK"] = self._sync
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
        for name in ("keep", "reject", "like", "love"):
            (self.tmp / name).mkdir(exist_ok=True)
        incoming = self.tmp / "incoming"
        incoming.mkdir()
        rel = "incoming/a.jpg"
        (self.tmp / rel).write_bytes(b"photo-bytes")
        deck = resolve(self.tmp).decks[0]
        scan_incremental(deck)
        return deck, rel

    def test_move_not_complete_while_source_remains(self):
        (self.tmp / "incoming").mkdir(exist_ok=True)
        (self.tmp / "like").mkdir(exist_ok=True)
        src = self.tmp / "incoming" / "b.jpg"
        dest = self.tmp / "like" / "b.jpg"
        payload = b"x"
        src.write_bytes(payload)
        dest.write_bytes(payload)
        with patch(
            "choice.file_moves.remove_source",
            side_effect=MoveNotReady("source locked"),
        ):
            with self.assertRaises(MoveNotReady):
                move_file(src, dest)
        self.assertTrue(src.is_file())
        self.assertTrue(dest.is_file())

    def test_stranded_duplicate_after_kill_reconcile(self):
        deck, rel = self._sort_deck()
        decide(deck, rel, "up", None)
        wait_idle(deck.state_dir, timeout=60.0)
        src = self.tmp / rel
        dest = self.tmp / "like" / "a.jpg"
        self.assertTrue(dest.is_file())
        self.assertFalse(src.is_file())
        src.write_bytes(dest.read_bytes())
        _save_jobs(deck.state_dir, [])
        drop_memory_state(deck.state_dir)
        self.assertEqual(_unsorted_incoming(self.tmp), 1)
        self.assertEqual(len(load_index(deck.state_dir).ordered), 0)
        boot_deck(deck)
        wait_idle(deck.state_dir, timeout=60.0)
        self.assertFalse(src.is_file())
        self.assertTrue(dest.is_file())
        on_disk = _unsorted_incoming(self.tmp)
        self.assertEqual(len(load_index(deck.state_dir).ordered), on_disk)
        self.assertEqual(on_disk, 0)
        self.assertEqual(len(_read_log(deck)), 1)

    def test_locked_delete_retries_after_restart(self):
        os.environ.pop("CHOICE_SYNC_WORK", None)
        deck, rel = self._sort_deck()
        decide(deck, rel, "up", None)
        wait_idle(deck.state_dir, timeout=60.0)
        src = self.tmp / rel
        dest = self.tmp / "like" / "a.jpg"
        src.write_bytes(dest.read_bytes())
        _save_jobs(deck.state_dir, [])
        drop_memory_state(deck.state_dir)
        calls = {"n": 0}
        real_remove = remove_source

        def _flaky(path: Path) -> None:
            calls["n"] += 1
            if calls["n"] == 1:
                raise MoveNotReady("locked")
            real_remove(path)

        with patch("choice.work_queue.remove_source", side_effect=_flaky):
            reconcile_deck(deck)
            self.assertTrue(src.is_file())
            wait_idle(deck.state_dir, timeout=60.0)
        self.assertFalse(src.is_file())
        on_disk = _unsorted_incoming(self.tmp)
        self.assertEqual(len(load_index(deck.state_dir).ordered), on_disk)
        self.assertEqual(on_disk, 0)
