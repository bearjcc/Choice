# SPDX-License-Identifier: AGPL-3.0-only

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from choice.act import decide, index_summary, progress, save_deck_counts, undo
from choice.count_prefs import (
    counts_hidden,
    decided_today,
    load_counts_mode,
    save_counts_mode,
    today_count_label,
    write_folder_stats,
)
from choice.folder_index import load_index, scan_incremental, summary
from choice.load import Deck, resolve


class CountPrefsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _folder_deck(self, extra: dict | None = None, files: int = 2):
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
        for i in range(files):
            (self.tmp / f"p{i}.jpg").write_bytes(b"x")
        deck = resolve(self.tmp).decks[0]
        scan_incremental(deck)
        return deck

    def test_mode_on_shows_pile_counts(self):
        deck = self._folder_deck({"counts": "on"})
        save_counts_mode(deck, "on")
        snap = index_summary(deck)
        self.assertTrue(snap.get("meter"))
        self.assertEqual(snap.get("left"), 2)

    def test_mode_off_hides_counts_and_skips_scan_for_summary(self):
        deck = self._folder_deck()
        save_counts_mode(deck, "off")
        with patch("choice.folder_index.kick_background_scan") as kicked:
            snap = summary(deck, set(), counts_hidden=True)
        kicked.assert_not_called()
        self.assertFalse(snap.get("meter"))
        self.assertIsNone(snap.get("left"))
        home = index_summary(deck)
        self.assertFalse(home.get("meter"))
        self.assertIsNone(home.get("total"))

    def test_mode_off_progress_hides_meter(self):
        deck = self._folder_deck()
        save_counts_mode(deck, "off")
        snap = progress(deck, pending=True, limit=5, offset=0)
        self.assertFalse(snap.get("meter"))
        self.assertTrue(snap.get("counts_hidden"))
        self.assertEqual(len(snap["items"]), 2)

    def test_auto_hides_story_deck(self):
        deck = self._folder_deck(files=1)
        deck.story = {"start": "scene"}
        self.assertTrue(counts_hidden(deck))
        snap = index_summary(deck)
        self.assertFalse(snap.get("meter"))

    def test_auto_hides_large_pile_from_stats(self):
        deck = self._folder_deck(files=3)
        write_folder_stats(deck.state_dir, 6000)
        self.assertTrue(counts_hidden(deck))
        snap = index_summary(deck)
        self.assertFalse(snap.get("meter"))
        self.assertIsNone(snap.get("total"))

    def test_auto_shows_small_folder(self):
        deck = self._folder_deck(files=3)
        write_folder_stats(deck.state_dir, 3)
        self.assertFalse(counts_hidden(deck))
        snap = index_summary(deck)
        self.assertTrue(snap.get("meter"))
        self.assertEqual(snap.get("left"), 3)

    def test_decided_today_label_after_swipe(self):
        deck = self._folder_deck(files=1)
        save_counts_mode(deck, "off")
        decide(deck, "p0.jpg", "right", None)
        snap = index_summary(deck)
        self.assertIn("today", (snap.get("count_label") or "").lower())

    def test_decided_today_ignores_undone_swipes(self):
        deck = self._folder_deck(files=2)
        save_counts_mode(deck, "off")
        decide(deck, "p0.jpg", "right", None)
        self.assertEqual(decided_today(deck), 1)
        self.assertIsNotNone(today_count_label(deck))
        undo(deck)
        self.assertEqual(decided_today(deck), 0)
        self.assertIsNone(today_count_label(deck))

    def test_save_deck_counts_api(self):
        deck = self._folder_deck()
        out = save_deck_counts(deck, {"mode": "on"})
        self.assertTrue(out.get("ok"))
        self.assertEqual(load_counts_mode(deck), "on")

    def test_defaults_from_deck_json(self):
        deck = self._folder_deck({"counts": "off"})
        self.assertEqual(load_counts_mode(deck), "off")

    def test_auto_hides_rated_contest(self):
        deck = self._folder_deck(files=1)
        deck.contest_kind = "rated"
        self.assertTrue(counts_hidden(deck))

    def test_auto_hides_endless_plugin(self):
        deck = self._folder_deck(files=1)
        deck.plugin = object()
        deck.folder_scan = None
        self.assertTrue(counts_hidden(deck))

    def test_auto_shows_finite_plugin_list(self):
        from tests.test_plugin_pile_counts import PluginPileCountsTests

        helper = PluginPileCountsTests()
        helper.setUp()
        try:
            deck = helper._deck("hides_decided")
            deck.load_items()
            self.assertFalse(counts_hidden(deck))
        finally:
            helper.tearDown()
