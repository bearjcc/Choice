# SPDX-License-Identifier: AGPL-3.0-only

import statistics
import tempfile
import threading
import time
import unittest
from pathlib import Path

from choice.act import index_summary, progress
from choice.folder_index import scan_incremental
from choice.open import open_config


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
    def test_large_deck_index_and_items_stay_fast_while_growing(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
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
            scan_incremental(deck)
            growth = root / "batch099"
            stop = threading.Event()

            def _add_files():
                i = 0
                while not stop.is_set():
                    path = growth / f"growth{i:06d}.jpg"
                    path.write_bytes(b"y")
                    i += 1
                    time.sleep(0.004)

            thread = threading.Thread(target=_add_files, daemon=True)
            thread.start()
            index_times: list[float] = []
            item_times: list[float] = []
            try:
                for _ in range(40):
                    t0 = time.perf_counter()
                    index_summary(deck)
                    index_times.append(time.perf_counter() - t0)
                for _ in range(20):
                    t0 = time.perf_counter()
                    progress(deck, pending=True, limit=200, offset=0)
                    item_times.append(time.perf_counter() - t0)
            finally:
                stop.set()
                thread.join(timeout=2.0)
            index_p95 = statistics.quantiles(index_times, n=20)[-1]
            items_p95 = statistics.quantiles(item_times, n=20)[-1]
            self.assertLess(index_p95, 0.10, f"index p95 {index_p95:.3f}s")
            self.assertLess(items_p95, 0.30, f"items p95 {items_p95:.3f}s")


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
            self.assertLess(elapsed, 1.0, f"incremental scan took {elapsed:.2f}s")
