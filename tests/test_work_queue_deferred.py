# SPDX-License-Identifier: AGPL-3.0-only

import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from choice.act import decide
from choice.file_moves import MoveNotReady, move_file
from choice.folder_index import scan_incremental
from choice.load import resolve
from choice.work_queue import _mutate_jobs, boot_deck, wait_idle


class WorkQueueDeferredTests(unittest.TestCase):
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

    def _burst_deck(self, n_files: int):
        import json

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
        for name in ("keep", "reject"):
            (self.tmp / name).mkdir(exist_ok=True)
        incoming = self.tmp / "incoming"
        incoming.mkdir()
        ids: list[str] = []
        for i in range(n_files):
            rel = f"incoming/f{i:04d}.jpg"
            (self.tmp / rel).write_bytes(b"x")
            ids.append(rel)
        deck = resolve(self.tmp).decks[0]
        scan_incremental(deck)
        return deck, ids

    def test_locked_file_does_not_block_other_decides(self):
        os.environ.pop("CHOICE_SYNC_WORK", None)
        deck, ids = self._burst_deck(51)
        locked = ids[0]
        real_move = move_file

        def gated_move(src: Path, dest: Path) -> None:
            rel = src.relative_to(deck.root.resolve()).as_posix()
            if rel == locked:
                raise MoveNotReady("WinError 32: The process cannot access the file")
            real_move(src, dest)

        boot_deck(deck)
        with patch("choice.file_moves.move_file", side_effect=gated_move):
            decide(deck, locked, "right", None)
            latencies: list[float] = []
            for rel in ids[1:51]:
                start = time.perf_counter()
                decide(deck, rel, "right", None)
                latencies.append(time.perf_counter() - start)
            if os.getenv("GITHUB_ACTIONS"):
                cap = 1.0 if os.name == "nt" else 0.20
            else:
                cap = 0.05
            self.assertLess(max(latencies), cap)
            wait_idle(deck.state_dir, timeout=120.0)
            for rel in ids[1:]:
                self.assertFalse((deck.root / rel).is_file())

        def _clear_retry(jobs):
            for job in jobs:
                op = job.file_op or {}
                if op.get("from") == locked and job.status == "pending":
                    job.retry_after = 0.0

        _mutate_jobs(deck.state_dir, _clear_retry)
        wait_idle(deck.state_dir, timeout=60.0)
        self.assertFalse((deck.root / locked).is_file())


if __name__ == "__main__":
    unittest.main()
