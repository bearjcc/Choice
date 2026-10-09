# SPDX-License-Identifier: AGPL-3.0-only

import json
import tempfile
import unittest
from pathlib import Path

from choice.act import decide, progress, undo
from choice.folder_index import scan_incremental
from choice.load import resolve
from choice.open import open_config


class UndoPolicyTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _deck(self, extra: dict | None = None):
        data = {
            "source": {"type": "images", "path": ".", "recursive": True},
            "directions": {
                "right": {"label": "Yes", "value": "yes"},
                "left": {"label": "No", "value": "no"},
            },
        }
        if extra:
            data.update(extra)
        (self.tmp / "deck.json").write_text(json.dumps(data), encoding="utf-8")
        (self.tmp / "a.jpg").write_bytes(b"x")
        deck = resolve(self.tmp).decks[0]
        scan_incremental(deck)
        return deck

    def test_allow_undo_false_rejects_undo(self):
        deck = self._deck({"allow_undo": False})
        decide(deck, "a.jpg", "right", None)
        result = undo(deck)
        self.assertFalse(result.get("ok"))
        self.assertIn("disabled", (result.get("message") or "").lower())

    def test_progress_reports_undo_disabled(self):
        deck = self._deck({"allow_undo": False})
        snap = progress(deck, pending=True, limit=10, offset=0)
        self.assertFalse(snap.get("allow_undo"))
        self.assertFalse(snap.get("can_undo"))
        self.assertIsNone(snap.get("undo_hint"))

    def test_progress_includes_undo_hint_when_allowed(self):
        deck = self._deck()
        decide(deck, "a.jpg", "right", None)
        snap = progress(deck, pending=True, limit=10, offset=0)
        self.assertTrue(snap.get("allow_undo"))
        self.assertTrue(snap.get("can_undo"))
        hint = snap.get("undo_hint")
        self.assertIsNotNone(hint)
        self.assertEqual(hint.get("item"), "a.jpg")
        self.assertEqual(hint.get("direction"), "right")

    def test_choice_toml_default_allow_undo(self):
        root = self.tmp / "lib"
        root.mkdir()
        (root / "x.jpg").write_bytes(b"y")
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
id = "quiz"
title = "Quiz"
source = "f"
mount = "."
allow_undo = false
""".strip(),
            encoding="utf-8",
        )
        deck = open_config(cfg).decks[0]
        self.assertFalse(deck.allow_undo)
