# SPDX-License-Identifier: AGPL-3.0-only

import json
import os
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from choice.act import _read_log, decide, index_summary
from choice.folder_index import load_index, scan_incremental
from choice.load import Deck, resolve
from choice.work_queue import boot_deck, drop_memory_state, wait_idle


def _unsorted_incoming(root: Path) -> int:
    incoming = root / "incoming"
    if not incoming.is_dir():
        return 0
    return sum(1 for p in incoming.iterdir() if p.is_file() and not p.name.startswith("."))


def _logged_sort_decisions(deck) -> int:
    undone = {row.get("ref") for row in _read_log(deck) if row.get("type") == "undo"}
    n = 0
    for row in _read_log(deck):
        if row.get("type") != "decision" or row.get("id") in undone:
            continue
        if row.get("later"):
            continue
        if isinstance(row.get("file_op"), dict):
            n += 1
    return n


class WorkQueueConcurrentTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._sync = os.environ.get("CHOICE_SYNC_WORK")

    def tearDown(self):
        if self._sync is None:
            os.environ.pop("CHOICE_SYNC_WORK", None)
        else:
            os.environ["CHOICE_SYNC_WORK"] = self._sync
        for queue_file in self.tmp.rglob("work_queue.json"):
            wait_idle(queue_file.parent, timeout=60.0)
        try:
            self._tmp.cleanup()
        except OSError:
            time.sleep(0.25)
            self._tmp.cleanup()

    def _burst_deck(self, n_files: int):
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
        ids: list[str] = []
        for i in range(n_files):
            rel = f"incoming/f{i:04d}.jpg"
            (self.tmp / rel).write_bytes(b"x")
            ids.append(rel)
        deck = resolve(self.tmp).decks[0]
        scan_incremental(deck)
        return deck, ids

    def _assert_consistent(self, deck: Deck, n_decided: int, timeout: float = 120.0) -> None:
        deadline = time.monotonic() + timeout
        last: AssertionError | None = None
        while time.monotonic() < deadline:
            wait_idle(deck.state_dir, timeout=min(5.0, deadline - time.monotonic()))
            try:
                logged = _logged_sort_decisions(deck)
                self.assertEqual(logged, n_decided)
                on_disk = _unsorted_incoming(self.tmp)
                snap = index_summary(deck)
                left = snap.get("left")
                idx = load_index(deck.state_dir)
                self.assertEqual(len(idx.ordered), on_disk)
                if left is not None:
                    self.assertEqual(left, on_disk)
                self.assertEqual(on_disk, 0)
                return
            except AssertionError as exc:
                last = exc
                time.sleep(0.05)
        if last is not None:
            raise last
        raise AssertionError("queue did not settle")

    def test_burst_three_hundred_decides(self):
        os.environ.pop("CHOICE_SYNC_WORK", None)
        deck, ids = self._burst_deck(300)
        directions = ("right", "left", "up", "down")

        def _one(rel: str) -> None:
            decide(deck, rel, directions[hash(rel) % 4], None)

        with ThreadPoolExecutor(max_workers=16) as pool:
            futures = [pool.submit(_one, rel) for rel in ids]
            for fut in as_completed(futures):
                fut.result()
        self._assert_consistent(deck, 300)

    def test_burst_restart_reconcile(self):
        os.environ.pop("CHOICE_SYNC_WORK", None)
        deck, ids = self._burst_deck(300)
        errors: list[Exception] = []

        def _one(rel: str) -> None:
            try:
                decide(deck, rel, "right", None)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_one, args=(rel,)) for rel in ids]
        for t in threads:
            t.start()
        drop_memory_state(deck.state_dir)
        boot_deck(deck)
        for t in threads:
            t.join(timeout=120)
        self.assertEqual(errors, [])
        self.assertTrue(wait_idle(deck.state_dir, timeout=120.0))
        self._assert_consistent(deck, 300)
