# SPDX-License-Identifier: AGPL-3.0-only

import json
import tempfile
import unittest
from pathlib import Path

from choice.act import decide, progress, undo
from choice.folder_deck import items_from_folder_scan, parse_folder_options
from choice.load import resolve
from choice.open import open_config


class FolderSourceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_results_mode_does_not_move_files(self):
        (self.tmp / "a.png").write_bytes(b"x")
        deck = resolve(self.tmp).decks[0]
        self.assertEqual(deck.directions["left"].does, "label")
        decide(deck, "a.png", "left", None)
        self.assertTrue((self.tmp / "a.png").is_file())
        snap = progress(deck, pending=True)
        self.assertEqual(snap["left"], 0)

    def test_sort_mode_moves_to_target_and_undoes(self):
        (self.tmp / "deck.json").write_text(
            json.dumps(
                {
                    "title": "Sort",
                    "source": {
                        "type": "images",
                        "path": ".",
                        "output": "sort",
                        "sort": {"right": "keep", "left": "bin"},
                    },
                    "directions": {
                        "right": {"label": "Keep", "value": "keep"},
                        "left": {"label": "Bin", "value": "bin"},
                        "down": {"label": "Skip", "value": "skip", "later": True},
                    },
                }
            ),
            encoding="utf-8",
        )
        (self.tmp / "pic.png").write_bytes(b"png")
        deck = resolve(self.tmp).decks[0]
        self.assertEqual(deck.directions["right"].does, "move")
        self.assertEqual(deck.directions["right"].into, "keep")
        result = decide(deck, "pic.png", "right", None)
        self.assertTrue(result["ok"], result)
        self.assertFalse((self.tmp / "pic.png").exists())
        self.assertTrue((self.tmp / "keep" / "pic.png").is_file())
        undone = undo(deck)
        self.assertTrue(undone["ok"], undone)
        self.assertTrue((self.tmp / "pic.png").is_file())

    def test_sort_collision_renames_destination(self):
        (self.tmp / "deck.json").write_text(
            json.dumps(
                {
                    "source": {
                        "type": "files",
                        "path": ".",
                        "output": "sort",
                        "sort": {"right": "keep"},
                    }
                }
            ),
            encoding="utf-8",
        )
        (self.tmp / "keep").mkdir()
        (self.tmp / "keep" / "dup.txt").write_text("old", encoding="utf-8")
        (self.tmp / "dup.txt").write_text("new", encoding="utf-8")
        deck = resolve(self.tmp).decks[0]
        decide(deck, "dup.txt", "right", None)
        self.assertTrue((self.tmp / "keep" / "dup_1.txt").is_file())

    def test_recursive_skips_sort_target_folders(self):
        (self.tmp / "deck.json").write_text(
            json.dumps(
                {
                    "source": {
                        "type": "files",
                        "path": ".",
                        "output": "sort",
                        "recursive": True,
                        "sort": {"right": "keep"},
                    }
                }
            ),
            encoding="utf-8",
        )
        (self.tmp / "keep").mkdir()
        (self.tmp / "keep" / "hidden.txt").write_text("nope", encoding="utf-8")
        (self.tmp / "sub").mkdir()
        (self.tmp / "sub" / "show.txt").write_text("yes", encoding="utf-8")
        deck = resolve(self.tmp).decks[0]
        items, _w = deck.load_items()
        ids = {item.id for item in items}
        self.assertIn("sub/show.txt", ids)
        self.assertNotIn("keep/hidden.txt", ids)

    def test_include_glob(self):
        scan = parse_folder_options({"include": ["*.png"]})
        (self.tmp / "a.png").write_bytes(b"1")
        (self.tmp / "b.txt").write_text("t", encoding="utf-8")
        items = items_from_folder_scan(self.tmp, self.tmp, scan)
        self.assertEqual([i.id for i in items], ["a.png"])

    def test_config_folder_deck(self):
        inbox = self.tmp / "inbox"
        inbox.mkdir()
        (inbox / "one.jpg").write_bytes(b"j")
        cfg = self.tmp / "choice.toml"
        cfg.write_text(
            """
[state]
dir = "state"

[[sources]]
id = "local"
type = "folder"
path = "."

[[decks]]
id = "inbox"
title = "Inbox"
source = "local"
mount = "inbox"
output = "sort"
recursive = true
sort_right = "keep"
sort_left = "reject"
include = ["*.jpg"]
""",
            encoding="utf-8",
        )
        opened = open_config(cfg)
        deck = next(d for d in opened.decks if d.id == "inbox")
        items, _w = deck.load_items()
        self.assertEqual(len(items), 1)
        decide(deck, items[0].id, "right", None)
        self.assertTrue((inbox / "keep" / "one.jpg").is_file())


if __name__ == "__main__":
    unittest.main()
