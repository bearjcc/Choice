# SPDX-License-Identifier: AGPL-3.0-only

import json
import os
import tempfile
import unittest
from pathlib import Path

from choice.act import _read_log, decide, progress, undo
from choice.folder_index import scan_incremental
from choice.load import resolve
from choice.open import open_config

FIX = Path(__file__).resolve().parent / "fixtures" / "plugin_host"
ROOT = Path(__file__).resolve().parents[1]


class UndoOverhaul064Tests(unittest.TestCase):
    def test_plugin_noop_undo_ok_false_logs_undo(self):
        with tempfile.TemporaryDirectory() as tmpname:
            tmp = Path(tmpname)
            cfg = tmp / "choice.toml"
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
mount = "reorder_list"
""".strip(),
                encoding="utf-8",
            )
            os.environ["CHOICE_DISABLE_WARM"] = "1"
            try:
                deck = open_config(cfg).decks[0]
                deck.load_items()
                decide(deck, "card-a", "right", None)
                snap = progress(deck, pending=True, limit=10, offset=0)
                self.assertTrue(snap.get("can_undo"))
                result = undo(deck, "card-a", snap["undo_hint"]["decision_id"])
                self.assertTrue(result.get("ok"))
                snap2 = progress(deck, pending=True, limit=10, offset=0)
                self.assertFalse(snap2.get("can_undo"))
                records = _read_log(deck)
                self.assertTrue(any(r.get("type") == "undo" for r in records))
            finally:
                os.environ.pop("CHOICE_DISABLE_WARM", None)

    def test_undo_requires_matching_decision_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.jpg").write_bytes(b"x")
            (root / "b.jpg").write_bytes(b"y")
            (root / "deck.json").write_text(
                json.dumps(
                    {
                        "source": {"type": "images", "path": ".", "recursive": True},
                        "directions": {
                            "right": {"label": "Yes", "value": "yes"},
                            "left": {"label": "No", "value": "no"},
                        },
                    }
                ),
                encoding="utf-8",
            )
            deck = resolve(root).decks[0]
            scan_incremental(deck)
            decide(deck, "a.jpg", "right", None)
            decide(deck, "b.jpg", "right", None)
            snap = progress(deck, pending=True, limit=10, offset=0)
            hint = snap["undo_hint"]
            self.assertEqual(hint["item"], "b.jpg")
            bad = undo(deck, "b.jpg", "not-a-real-token")
            self.assertFalse(bad.get("ok"))
            good = undo(deck, hint["item"], hint["decision_id"])
            self.assertTrue(good.get("ok"))

    def test_undo_later_skip_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.jpg").write_bytes(b"x")
            (root / "deck.json").write_text(
                json.dumps(
                    {
                        "source": {"type": "images", "path": ".", "recursive": True},
                        "directions": {
                            "right": {"label": "Yes", "value": "yes"},
                            "down": {"label": "Later", "value": "later", "later": True},
                        },
                    }
                ),
                encoding="utf-8",
            )
            deck = resolve(root).decks[0]
            scan_incremental(deck)
            out = decide(deck, "a.jpg", "down", None)
            self.assertTrue(out.get("ok"))
            snap = progress(deck, pending=True, limit=10, offset=0)
            self.assertTrue(snap.get("can_undo"))
            hint = snap["undo_hint"]
            self.assertTrue(hint.get("later"))
            undone = undo(deck, hint["item"], hint["decision_id"])
            self.assertTrue(undone.get("ok"))


class UndoClientRegression064(unittest.TestCase):
    def test_client_undo_overhaul_wiring(self):
        text = (ROOT / "choice" / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("undoStack", text)
        self.assertIn("queueDecideSave", text)
        self.assertIn("restoreUndoAtPos", text)
        self.assertIn("MEDIA_BLOB_MAX = 30", text)
        self.assertIn("state.pending = true", text)
        self.assertIn("decision_id", text)
        self.assertNotIn("DECIDE_HISTORY_MAX", text)
        self.assertNotIn("state.undoInFlight", text)
        self.assertIn("showSeq", text)

    def test_undo_posts_item_and_decision_id_not_empty_object(self):
        text = (ROOT / "choice" / "web" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn('api(undoPath, {})', text.replace(" ", ""))
        self.assertIn("decision_id:", text)

    def test_pile_nav_merge_pin_and_restore_at_pos(self):
        nav = (ROOT / "choice" / "web" / "pile_nav.js").read_text(encoding="utf-8")
        self.assertIn("restoreUndoAtPos", nav)
        self.assertIn("pin && pin.id", nav)


if __name__ == "__main__":
    unittest.main()
