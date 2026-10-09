# SPDX-License-Identifier: AGPL-3.0-only

import json
import tempfile
import unittest
from pathlib import Path

from choice.act import progress
from choice.folder_index import scan_incremental
from choice.load import resolve, swipe_item_public
from choice.open import open_config


class ShowFilenameTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _image_deck(self, extra: dict | None = None):
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
        (self.tmp / "vacation.jpg").write_bytes(b"x")
        deck = resolve(self.tmp).decks[0]
        scan_incremental(deck)
        return deck

    def test_default_hides_filename_in_progress(self):
        deck = self._image_deck()
        self.assertFalse(deck.show_filename)
        snap = progress(deck, pending=True, limit=5, offset=0)
        row = snap["items"][0]
        self.assertNotIn("file", row)
        self.assertEqual(row.get("title"), "")

    def test_show_filename_opt_in(self):
        deck = self._image_deck({"show_filename": True})
        self.assertTrue(deck.show_filename)
        snap = progress(deck, pending=True, limit=5, offset=0)
        row = snap["items"][0]
        self.assertEqual(row.get("file"), "vacation.jpg")
        self.assertEqual(row.get("title"), "vacation.jpg")

    def test_choice_toml_show_filename(self):
        root = self.tmp / "photos"
        root.mkdir()
        (root / "a.jpg").write_bytes(b"x")
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
show_filename = true
""".strip(),
            encoding="utf-8",
        )
        deck = open_config(cfg).decks[0]
        scan_incremental(deck)
        self.assertTrue(deck.show_filename)
        item = deck.load_items()[0][0]
        row = swipe_item_public(deck, item, None)
        self.assertEqual(row.get("file"), "a.jpg")
        self.assertEqual(row.get("title"), "a.jpg")

    def test_quiz_title_unaffected_when_hidden(self):
        (self.tmp / "items.jsonl").write_text(
            '{"id":"1","q":"What is 2+2?"}\n',
            encoding="utf-8",
        )
        (self.tmp / "deck.json").write_text(
            json.dumps(
                {
                    "source": {"type": "jsonl", "path": "items.jsonl"},
                    "directions": {
                        "right": {"label": "Yes", "value": "yes"},
                        "left": {"label": "No", "value": "no"},
                    },
                }
            ),
            encoding="utf-8",
        )
        deck = resolve(self.tmp).decks[0]
        item = deck.load_items()[0][0]
        row = swipe_item_public(deck, item, None)
        self.assertIn("2+2", row.get("title") or "")
