# SPDX-License-Identifier: AGPL-3.0-only

import json
import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from choice.act import _read_log, decide, index_summary
from choice.folder_index import load_index, scan_incremental
from choice.load import resolve
from choice.work_queue import _save_jobs, boot_deck, drop_memory_state, reconcile_deck, wait_idle


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


def _unsorted_outside_sort(root: Path, deck) -> int:
    scan = deck.folder_scan
    assert scan is not None
    skip = {p.resolve() for p in scan.sort_dirs(root.resolve())}
    skip.add((root / ".choice").resolve())
    n = 0
    for path in root.rglob("*"):
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.name in {"deck.json"}:
            continue
        resolved = path.resolve()
        if any(resolved == s or str(resolved).startswith(str(s) + os.sep) for s in skip):
            continue
        if ".choice" in path.parts:
            continue
        n += 1
    return n


class DestCollisionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.tmp = Path(self._tmp.name)
        self._sync = os.environ.get("CHOICE_SYNC_WORK")
        self._deck = None

    def tearDown(self):
        if self._deck is not None:
            os.environ["CHOICE_SYNC_WORK"] = "1"
            wait_idle(self._deck.state_dir, timeout=120.0)
        if self._sync is None:
            os.environ.pop("CHOICE_SYNC_WORK", None)
        else:
            os.environ["CHOICE_SYNC_WORK"] = self._sync
        self._tmp.cleanup()

    def _sort_deck(self, n_folders: int, name: str = "img_0079.jpg"):
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
        for folder in ("keep", "reject", "like", "love"):
            (self.tmp / folder).mkdir(exist_ok=True)
        ids: list[str] = []
        for i in range(n_folders):
            d = self.tmp / f"d{i:02d}"
            d.mkdir()
            rel = f"d{i:02d}/{name}"
            (self.tmp / rel).write_bytes(f"payload-{i}".encode())
            ids.append(rel)
        deck = resolve(self.tmp).decks[0]
        scan_incremental(deck)
        self._deck = deck
        return deck, ids

    def _assert_consistent(self, deck, n_decided: int) -> None:
        wait_idle(deck.state_dir, timeout=180.0)
        logged = _logged_sort_decisions(deck)
        self.assertEqual(logged, n_decided)
        on_disk = _unsorted_outside_sort(self.tmp, deck)
        idx = load_index(deck.state_dir)
        self.assertEqual(len(idx.ordered), on_disk)
        snap = index_summary(deck)
        left = snap.get("left")
        if left is not None:
            self.assertEqual(left, on_disk)
        self.assertEqual(on_disk, 0)

    def test_same_name_burst_restart(self):
        os.environ.pop("CHOICE_SYNC_WORK", None)
        deck, ids = self._sort_deck(40)
        errors: list[Exception] = []
        try:

            def _one(rel: str) -> None:
                try:
                    decide(deck, rel, "up", None)
                except Exception as exc:
                    errors.append(exc)

            threads = [threading.Thread(target=_one, args=(rel,)) for rel in ids]
            for t in threads:
                t.start()
            drop_memory_state(deck.state_dir)
            boot_deck(deck)
            for t in threads:
                t.join(timeout=180)
            self.assertEqual(errors, [])
            boot_deck(deck)
            self._assert_consistent(deck, len(ids))
        finally:
            os.environ["CHOICE_SYNC_WORK"] = "1"
            wait_idle(deck.state_dir, timeout=60.0)

    def test_false_done_reconcile(self):
        from choice.act import patch_decision_file_op

        deck, ids = self._sort_deck(2, name="img_0079.jpg")
        decide(deck, ids[0], "up", None)
        decide(deck, ids[1], "up", None)
        wait_idle(deck.state_dir, timeout=60.0)
        src1 = self.tmp / ids[1]
        self.assertFalse(src1.is_file())
        second = [r for r in _read_log(deck) if r.get("item") == ids[1]][0]
        decision_id = str(second.get("id"))
        stray = self.tmp / "like" / "img_0079_1.jpg"
        if stray.is_file():
            src1.write_bytes(stray.read_bytes())
            stray.unlink()
        else:
            src1.write_bytes(b"payload-1")
        patch_decision_file_op(
            deck,
            decision_id,
            {"op": "move", "from": ids[1], "to": "like/img_0079.jpg"},
        )
        _save_jobs(deck.state_dir, [])
        drop_memory_state(deck.state_dir)
        self.assertTrue(src1.is_file())
        reconcile_deck(deck)
        wait_idle(deck.state_dir, timeout=60.0)
        self.assertFalse(src1.is_file())
        like_dir = list((self.tmp / "like").iterdir())
        self.assertEqual(len(like_dir), 2)
        on_disk = _unsorted_outside_sort(self.tmp, deck)
        self.assertEqual(on_disk, 0)
