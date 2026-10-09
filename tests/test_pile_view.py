# SPDX-License-Identifier: AGPL-3.0-only

import json
import tempfile
import time
import unittest
from pathlib import Path

from choice.act import progress, save_deck_view
from choice.folder_index import load_index, scan_incremental
from choice.load import resolve
from choice.natsort import natural_key
from choice.pile_view import view_order_ids
from choice.view_prefs import ViewPrefs, load_view_prefs, pile_view_locked, save_view_prefs


class PileViewTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _deck(self, extra: dict | None = None):
        data = {
            "source": {
                "type": "images",
                "path": ".",
                "recursive": True,
                "output": "results",
            },
            "directions": {
                "right": {"label": "Yes", "value": "yes"},
                "left": {"label": "No", "value": "no"},
            },
        }
        if extra:
            data.update(extra)
        (self.tmp / "deck.json").write_text(json.dumps(data), encoding="utf-8")
        deck = resolve(self.tmp).decks[0]
        scan_incremental(deck)
        return deck

    def test_natural_sort_key(self):
        names = ["(12).jpg", "(117).jpg", "(118).jpg", "(119).jpg"]
        self.assertEqual(sorted(names, key=natural_key), names)

    def test_filename_sort_order(self):
        for name in ("a (12).jpg", "a (117).jpg", "a (119).jpg"):
            (self.tmp / name).write_bytes(b"x")
        deck = self._deck()
        idx = load_index(deck.state_dir)
        prefs = ViewPrefs(sort_mode="filename")
        order = view_order_ids(deck, idx, prefs)
        self.assertEqual([Path(p).name for p in order], sorted([Path(p).name for p in order], key=natural_key))

    def test_stable_random_across_pages(self):
        for i in range(20):
            (self.tmp / f"f{i:03d}.jpg").write_bytes(b"x")
        deck = self._deck({"view": {"sort_mode": "random", "random_seed": "test-seed"}})
        prefs = load_view_prefs(deck)
        full = progress(deck, pending=True, limit=0, offset=0)
        p1 = progress(deck, pending=True, limit=5, offset=0)["items"]
        p2 = progress(deck, pending=True, limit=5, offset=5)["items"]
        ids = [row["id"] for row in p1 + p2]
        idx = load_index(deck.state_dir)
        expected = view_order_ids(deck, idx, prefs)[:10]
        self.assertEqual(ids, expected)

    def test_mtime_desc(self):
        a = self.tmp / "old.jpg"
        b = self.tmp / "new.jpg"
        a.write_bytes(b"a")
        b.write_bytes(b"b")
        deck = self._deck()
        scan_incremental(deck)
        idx = load_index(deck.state_dir)
        b.touch()
        idx.meta["old.jpg"]["mtime_ns"] = 1
        idx.meta["new.jpg"]["mtime_ns"] = 9
        order = view_order_ids(deck, idx, ViewPrefs(sort_mode="mtime_desc"))
        self.assertEqual(order[0], "new.jpg")

    def test_folder_filter(self):
        deck = self._deck()
        (self.tmp / "keep").mkdir()
        (self.tmp / "skip").mkdir()
        (self.tmp / "keep" / "a.jpg").write_bytes(b"x")
        (self.tmp / "skip" / "b.jpg").write_bytes(b"x")
        scan_incremental(deck)
        prefs = ViewPrefs(include_folders=["keep"])
        idx = load_index(deck.state_dir)
        order = view_order_ids(deck, idx, prefs)
        self.assertEqual(order, ["keep/a.jpg"])

    def test_file_type_filter(self):
        (self.tmp / "a.jpg").write_bytes(b"x")
        (self.tmp / "b.mp4").write_bytes(b"x")
        deck = self._deck()
        scan_incremental(deck)
        idx = load_index(deck.state_dir)
        order = view_order_ids(deck, idx, ViewPrefs(file_types=["image"]))
        self.assertEqual(order, ["a.jpg"])

    def test_locked_contest_ignores_sort(self):
        (self.tmp / "deck.json").write_text(
            json.dumps(
                {
                    "source": {"type": "jsonl", "path": "items.jsonl"},
                    "contest": {"kind": "robin"},
                    "directions": {
                        "right": {"label": "A", "value": "a"},
                        "left": {"label": "B", "value": "b"},
                    },
                }
            ),
            encoding="utf-8",
        )
        (self.tmp / "items.jsonl").write_text(
            '{"name":"x"}\n{"name":"y"}\n',
            encoding="utf-8",
        )
        deck = resolve(self.tmp).decks[0]
        self.assertTrue(pile_view_locked(deck))
        save_view_prefs(deck, ViewPrefs(sort_mode="filename"))
        self.assertEqual(load_view_prefs(deck).sort_mode, "scan")

    def test_save_prefs_to_state_dir(self):
        deck = self._deck()
        result = save_deck_view(deck, {"sort_mode": "filename", "file_types": ["image"]})
        self.assertTrue(result["ok"])
        path = deck.state_dir / "view_prefs.json"
        self.assertTrue(path.is_file())
        self.assertEqual(load_view_prefs(deck).sort_mode, "filename")

    def test_view_sort_perf_30k(self):
        deck = self._deck()
        for d in range(50):
            (self.tmp / f"d{d}").mkdir(exist_ok=True)
        for i in range(30_000):
            (self.tmp / f"d{i % 50}" / f"f{i:05d}.jpg").write_bytes(b"x")
        scan_incremental(deck)
        idx = load_index(deck.state_dir)
        prefs = ViewPrefs(sort_mode="filename")
        t0 = time.perf_counter()
        order = view_order_ids(deck, idx, prefs)
        elapsed = time.perf_counter() - t0
        self.assertEqual(len(order), 30_000)
        self.assertLess(elapsed, 3.0)
        t1 = time.perf_counter()
        order2 = view_order_ids(deck, idx, prefs)
        self.assertLess(time.perf_counter() - t1, 0.05)
        self.assertEqual(order2, order)
