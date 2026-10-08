# SPDX-License-Identifier: AGPL-3.0-only

import json
import os
import tempfile
import unittest
from pathlib import Path

from choice.act import decide, import_swipe_legacy, progress
from choice.open import open_config
from choice.swipe_log import read_events, replay_decisions, swipe_remaining_count


class SwipeReplayTests(unittest.TestCase):
    def test_replay_undo_and_reswipe(self):
        events = [
            {"type": "swipe", "seq": 1, "item_id": "a", "action": "right"},
            {"type": "swipe", "seq": 2, "item_id": "b", "action": "left"},
            {"type": "undo", "ref": 2, "item_id": "b", "ok": True},
            {"type": "swipe", "seq": 3, "item_id": "b", "action": "right"},
        ]
        decided = replay_decisions(events)
        self.assertEqual(set(decided), {"a", "b"})
        self.assertEqual(decided["a"]["action"], "right")
        self.assertEqual(decided["b"]["action"], "right")
        remaining = swipe_remaining_count({"a", "b", "c"}, events)
        self.assertEqual(remaining, 1)


class LegacyLogIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.events = self.tmp / "hist.events.jsonl"
        lines = [
            {"type": "swipe", "seq": 1, "item_id": "a", "action": "right"},
            {"type": "swipe", "seq": 2, "item_id": "b", "action": "left"},
            {"type": "undo", "ref": 2, "item_id": "b", "ok": True},
            {"type": "swipe", "seq": 3, "item_id": "b", "action": "right"},
        ]
        with self.events.open("w", encoding="utf-8") as handle:
            for row in lines:
                handle.write(json.dumps(row) + "\n")
        swipe_root = Path(__file__).resolve().parent / "fixtures" / "swipe_history"
        config = self.tmp / "choice.toml"
        config.write_text(
            f"""
[state]
dir = ".choice-state"

[[sources]]
id = "swipe"
type = "swipe"
path = "{swipe_root.parent.as_posix()}"

[[decks]]
id = "hist"
title = "History"
source = "swipe"
mount = "swipe_history"
legacy_log = "{self.events.as_posix()}"
""".strip(),
            encoding="utf-8",
        )
        self.deck = open_config(config).decks[0]

    def test_remaining_matches_swipe(self):
        events = read_events(self.events)
        swipe_left = swipe_remaining_count({"a", "b", "c"}, events)
        snap = progress(self.deck, pending=True)
        self.assertTrue(snap.get("ok"))
        self.assertEqual(snap["left"], swipe_left)
        self.assertEqual(snap["decided"], 2)

    def test_import_idempotent(self):
        added1, _skip1 = import_swipe_legacy(self.deck)
        self.assertGreater(added1, 0)
        log = self.deck.state_dir / "decisions.jsonl"
        lines_after_first = log.read_text(encoding="utf-8").count("\n")
        added2, skipped2 = import_swipe_legacy(self.deck)
        self.assertEqual(added2, 0)
        self.assertGreater(skipped2, 0)
        lines_after_second = log.read_text(encoding="utf-8").count("\n")
        self.assertEqual(lines_after_first, lines_after_second)


class PluginOnceTests(unittest.TestCase):
    def test_one_label_line_per_decide(self):
        tmp = Path(tempfile.mkdtemp())
        label_path = tmp / "labels.jsonl"
        os.environ["LABEL_ONCE_PATH"] = str(label_path)
        deck_dir = Path(__file__).resolve().parent / "fixtures" / "label_once"
        config = tmp / "choice.toml"
        config.write_text(
            f"""
[state]
dir = ".choice-state"

[[sources]]
id = "swipe"
type = "swipe"
path = "{deck_dir.parent.as_posix()}"

[[decks]]
id = "labels"
title = "Labels"
source = "swipe"
mount = "label_once"
""".strip(),
            encoding="utf-8",
        )
        deck = open_config(config).decks[0]
        decide(deck, "only", "right", "")
        decide(deck, "only", "right", "")
        self.assertEqual(label_path.read_text(encoding="utf-8").count("\n"), 1)
        os.environ.pop("LABEL_ONCE_PATH", None)
