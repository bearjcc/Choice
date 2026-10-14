# SPDX-License-Identifier: AGPL-3.0-only

import os
import statistics
import tempfile
import threading
import time
import unittest
from pathlib import Path

from choice.act import index_summary, progress
from choice.folder_index import scan_incremental, wait_folder_index_idle
from choice.open import open_config

# Heavy timing test: skipped on default GITHUB_ACTIONS matrix; run via CI perf job.
_RUN_PERF = os.getenv("CHOICE_RUN_PERF") == "1"
_SKIP_PERF_ON_CI = bool(os.getenv("GITHUB_ACTIONS")) and not _RUN_PERF


def _build_tree(root: Path, file_count: int, dir_count: int) -> None:
    root.mkdir(parents=True, exist_ok=True)
    per = max(1, file_count // dir_count)
    n = 0
    for d in range(dir_count):
        sub = root / f"batch{d:03d}"
        sub.mkdir(parents=True, exist_ok=True)
        for i in range(per):
            if n >= file_count:
                return
            (sub / f"f{n:06d}.jpg").write_bytes(b"x")
            n += 1


class FolderIndexPerfTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.tmp = Path(self._tmp.name)
        self._deck = None
        self._stop: threading.Event | None = None
        self._growth_thread: threading.Thread | None = None

    def tearDown(self):
        if self._stop is not None:
            self._stop.set()
        if self._growth_thread is not None:
            self._growth_thread.join(timeout=5.0)
        from choice.work_queue import wait_idle

        for queue in self.tmp.rglob("work_queue.json"):
            wait_idle(queue.parent, timeout=90.0)
        if self._deck is not None:
            wait_folder_index_idle(self._deck, timeout=90.0)
            wait_idle(self._deck.state_dir, timeout=90.0)
        time.sleep(0.75 if os.name == "nt" else 0.25)
        try:
            self._tmp.cleanup()
        except OSError:
            time.sleep(1.0)
            self._tmp.cleanup()

    @unittest.skipIf(
        _SKIP_PERF_ON_CI,
        "perf timing: run with CHOICE_RUN_PERF=1 (see .github/workflows/ci.yml perf job)",
    )
    def test_large_deck_index_and_items_stay_fast_while_growing(self):
        tmp_path = self.tmp
        root = tmp_path / "lib"
        _build_tree(root, 30800, 140)
        cfg = tmp_path / "choice.toml"
        cfg.write_text(
            f"""
[state]
dir = "state"

[[sources]]
id = "f"
type = "folder"
path = "{root.as_posix()}"

[[decks]]
id = "d"
title = "D"
source = "f"
mount = "."
type = "images"
recursive = true
""".strip(),
            encoding="utf-8",
        )
        deck = open_config(cfg).decks[0]
        self._deck = deck
        scan_incremental(deck)
        growth = root / "batch099"
        stop = threading.Event()
        self._stop = stop

        def _add_files():
            i = 0
            while not stop.is_set():
                path = growth / f"growth{i:06d}.jpg"
                path.write_bytes(b"y")
                i += 1
                time.sleep(0.004)

        thread = threading.Thread(target=_add_files, daemon=False)
        self._growth_thread = thread
        thread.start()
        index_times: list[float] = []
        item_times: list[float] = []
        for _ in range(40):
            t0 = time.perf_counter()
            index_summary(deck)
            index_times.append(time.perf_counter() - t0)
        for _ in range(20):
            t0 = time.perf_counter()
            progress(deck, pending=True, limit=200, offset=0)
            item_times.append(time.perf_counter() - t0)
        stop.set()
        thread.join(timeout=5.0)
        wait_folder_index_idle(deck, timeout=90.0)
        index_p95 = statistics.quantiles(index_times, n=20)[-1]
        items_p95 = statistics.quantiles(item_times, n=20)[-1]
        index_cap = 0.15 if os.getenv("GITHUB_ACTIONS") else 0.10
        items_cap = 0.45 if os.getenv("GITHUB_ACTIONS") else 0.30
        self.assertLess(index_p95, index_cap, f"index p95 {index_p95:.3f}s")
        self.assertLess(items_p95, items_cap, f"items p95 {items_p95:.3f}s")


class FolderIndexIncrementalTests(unittest.TestCase):
    def test_one_changed_dir_rescans_quickly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "lib"
            _build_tree(root, 5000, 50)
            cfg = Path(tmp) / "choice.toml"
            cfg.write_text(
                f"""
[state]
dir = "state"

[[sources]]
id = "f"
type = "folder"
path = "{root.as_posix()}"

[[decks]]
id = "d"
title = "D"
source = "f"
mount = "."
type = "images"
recursive = true
""".strip(),
                encoding="utf-8",
            )
            deck = open_config(cfg).decks[0]
            scan_incremental(deck)
            (root / "batch001" / "new.jpg").write_bytes(b"z")
            t0 = time.perf_counter()
            scan_incremental(deck)
            elapsed = time.perf_counter() - t0
            if os.getenv("GITHUB_ACTIONS"):
                cap = 8.0 if os.name == "nt" else 5.0
            else:
                cap = 3.0
            from choice.work_queue import wait_idle

            wait_idle(deck.state_dir, timeout=60.0)
            self.assertLess(elapsed, cap, f"incremental scan took {elapsed:.2f}s")
