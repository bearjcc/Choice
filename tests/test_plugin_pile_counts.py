# SPDX-License-Identifier: AGPL-3.0-only

import json
import os
import tempfile
import unittest
from pathlib import Path

from choice.act import index_summary, progress
from choice.deck_index import clear_index, plugin_pile_counts, refresh_persisted_summary
from choice.open import open_config

FIX = Path(__file__).resolve().parent / "fixtures" / "plugin_host"


class PluginPileCountsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        os.environ["CHOICE_DISABLE_WARM"] = "1"

    def tearDown(self):
        os.environ.pop("CHOICE_DISABLE_WARM", None)
        self._tmp.cleanup()

    def _config(self, mount: str) -> Path:
        cfg = self.tmp / "choice.toml"
        cfg.write_text(
            f"""
[state]
dir = "state"

[[sources]]
id = "swipe"
type = "swipe"
path = "{FIX.as_posix()}"

[[decks]]
id = "d"
title = "D"
source = "swipe"
mount = "{mount}"
""".strip(),
            encoding="utf-8",
        )
        return cfg

    def _deck(self, mount: str):
        return open_config(self._config(mount)).decks[0]

    def _write_log(self, deck, lines: list[str]):
        path = deck.state_dir / "decisions.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _assert_invariant(self, snap: dict):
        self.assertTrue(snap.get("ok"))
        total = snap["total"]
        decided = snap["decided"]
        left = snap["left"]
        self.assertIsNotNone(total)
        self.assertIsNotNone(left)
        self.assertEqual(total, decided + left)

    def test_formula_unit(self):
        universe = frozenset({"a", "b", "c"})
        log = {"gone-1", "gone-2"}
        plugin = frozenset({"b"})
        total, decided, left, list_size = plugin_pile_counts(log, universe, plugin)
        self.assertEqual(list_size, 3)
        self.assertEqual(decided, 3)
        self.assertEqual(left, 2)
        self.assertEqual(total, 5)

    def test_hides_decided_from_list(self):
        deck = self._deck("hides_decided")
        gone = [
            f'{{"type":"decision","id":"{i}","item":"gone-{i}","value":"right","later":false}}'
            for i in range(5)
        ]
        self._write_log(deck, gone)
        deck.load_items()
        snap = index_summary(deck)
        self._assert_invariant(snap)
        self.assertEqual(snap["decided"], 5)
        self.assertEqual(snap["left"], 3)
        self.assertEqual(snap["total"], 8)
        self.assertEqual(snap["list_size"], 3)

    def test_home_left_matches_items_pending(self):
        deck = self._deck("plugin_decided_mix")
        deck.load_items()
        home = index_summary(deck)
        items = progress(deck, pending=True, limit=200)
        self.assertEqual(home.get("left"), items.get("left"))
        self.assertEqual(home.get("total"), items.get("total"))

    def test_plugin_decided_without_log(self):
        deck = self._deck("plugin_decided_mix")
        self._write_log(
            deck,
            [
                '{"type":"decision","id":"1","item":"open-a","value":"right","later":false}',
            ],
        )
        deck.load_items()
        snap = index_summary(deck)
        self._assert_invariant(snap)
        self.assertEqual(snap["decided"], 3)
        self.assertEqual(snap["left"], 1)
        self.assertEqual(snap["total"], 4)

    def test_shrunk_list_many_log_entries(self):
        deck = self._deck("hides_decided")
        gone = [
            f'{{"type":"decision","id":"{i}","item":"hist-{i}","value":"right","later":false}}'
            for i in range(2133)
        ]
        self._write_log(deck, gone)
        deck.load_items()
        snap = index_summary(deck)
        self._assert_invariant(snap)
        self.assertEqual(snap["decided"], 2133)
        self.assertEqual(snap["left"], 3)
        self.assertEqual(snap["total"], 2136)

    def test_old_list_counts_upgrades_on_progress_not_index(self):
        deck = self._deck("decided_flag")
        counts = deck.state_dir / "list_counts.json"
        counts.parent.mkdir(parents=True, exist_ok=True)
        counts.write_text(
            json.dumps({"total": 504, "plugin_decided": ["done"]}),
            encoding="utf-8",
        )
        clear_index(deck)
        home = index_summary(deck)
        self._assert_invariant(home)
        self.assertEqual(home["left"], 503)
        saved = refresh_persisted_summary(deck)
        self.assertIsNotNone(saved)
        self.assertTrue(saved.ids)
        snap = index_summary(deck)
        self._assert_invariant(snap)
        self.assertEqual(snap["left"], 1)
        upgraded = json.loads(counts.read_text(encoding="utf-8"))
        self.assertIn("ids", upgraded)
        self.assertEqual(len(upgraded["ids"]), 2)

    def test_persisted_path_after_restart(self):
        deck = self._deck("hides_decided")
        self._write_log(
            deck,
            ['{"type":"decision","id":"1","item":"x","value":"right","later":false}'],
        )
        deck.load_items()
        clear_index(deck)
        reopened = open_config(self._config("hides_decided")).decks[0]
        snap = index_summary(reopened)
        self._assert_invariant(snap)
        self.assertEqual(snap["decided"], 1)
        self.assertEqual(snap["left"], 3)

    def test_refresh_persisted_summary_loads_ids(self):
        deck = self._deck("decided_flag")
        counts = deck.state_dir / "list_counts.json"
        counts.parent.mkdir(parents=True, exist_ok=True)
        counts.write_text('{"total": 99, "plugin_decided": []}', encoding="utf-8")
        saved = refresh_persisted_summary(deck)
        self.assertIsNotNone(saved)
        self.assertTrue(saved.ids)
