# SPDX-License-Identifier: AGPL-3.0-only

import tempfile
import time
import unittest
from pathlib import Path

from choice.act import index_summary
from choice.folder_deck import parse_folder_options
from choice.folder_list_cache import cached_list_files, folder_item_ids, invalidate_under
from choice.open import open_config


class FolderListCacheTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_subfolder_add_visible_after_invalidate(self):
        root = self.tmp / "lib"
        root.mkdir()
        (root / "top.jpg").write_bytes(b"x")
        sub = root / "nested"
        sub.mkdir()
        scan = parse_folder_options({"recursive": True, "type": "images"})
        first = folder_item_ids(root, scan)
        self.assertEqual(first, frozenset({"top.jpg"}))
        (sub / "new.jpg").write_bytes(b"y")
        invalidate_under(root)
        second = folder_item_ids(root, scan)
        self.assertIn("nested/new.jpg", second)

    def test_same_tick_add_changes_stamp(self):
        root = self.tmp / "lib"
        root.mkdir()
        skip_dirs = {(root / ".choice").resolve()}
        before = cached_list_files(root, False, skip_dirs)
        self.assertEqual(len(before), 0)
        for i in range(3):
            (root / f"f{i}.jpg").write_bytes(b"x")
        invalidate_under(root)
        after = cached_list_files(root, False, skip_dirs)
        self.assertEqual(len(after), 3)

    def test_index_summary_without_building_items(self):
        root = self.tmp / "photos"
        root.mkdir()
        for i in range(50):
            (root / f"p{i}.jpg").write_bytes(b"x")
        cfg = self.tmp / "choice.toml"
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
        from choice.folder_index import scan_incremental

        scan_incremental(deck)
        snap = index_summary(deck)
        self.assertTrue(snap.get("ok"))
        self.assertEqual(snap.get("list_size"), 50)
        self.assertEqual(snap["total"], snap["decided"] + snap["left"])


class FolderBenchmarkTests(unittest.TestCase):
    def test_list_twenty_k_under_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "big"
            root.mkdir()
            sub = root / "a" / "b"
            sub.mkdir(parents=True)
            for i in range(20000):
                (sub / f"f{i:05d}.jpg").write_bytes(b"x")
            scan = parse_folder_options({"recursive": True, "type": "images"})
            start = time.perf_counter()
            ids = folder_item_ids(root, scan)
            elapsed = time.perf_counter() - start
            self.assertEqual(len(ids), 20000)
            self.assertLess(elapsed, 8.0, f"listing took {elapsed:.2f}s")
