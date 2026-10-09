# SPDX-License-Identifier: AGPL-3.0-only

import tempfile
import unittest
from pathlib import Path

from choice.config import load_config, save_config
from choice.open_cache import bust_config, open_library
from choice.people import Person, drop_deck_from_roster, load_roster, save_roster


class RemoveDeckTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_drop_deck_from_roster(self):
        root = self.tmp
        save_roster(root, [Person("a", "A", ["keep", "gone"])])
        drop_deck_from_roster(root, "gone")
        roster = load_roster(root)
        self.assertEqual(roster.people[0].decks, ["keep"])

    def test_readd_deck_keeps_state_dir(self):
        cfg_path = self.tmp / "choice.toml"
        state = self.tmp / "state"
        cfg_path.write_text(
            f"""
[state]
dir = "{state.as_posix()}"

[[sources]]
id = "s"
type = "folder"
path = "."

[[decks]]
id = "d"
title = "D"
source = "s"
mount = "."
""".strip(),
            encoding="utf-8",
        )
        cfg = load_config(cfg_path)
        (state / "d").mkdir(parents=True)
        marker = state / "d" / "decisions.jsonl"
        marker.write_text('{"type":"decision","id":"1","item":"x","value":"y"}\n', encoding="utf-8")
        save_config(cfg, [{"id": "s", "type": "folder", "path": "."}], [])
        bust_config(cfg_path)
        opened = open_library(cfg_path)
        self.assertEqual(opened.decks, [])
        save_config(
            cfg,
            [{"id": "s", "type": "folder", "path": "."}],
            [{"id": "d", "title": "D", "source": "s", "mount": "."}],
        )
        bust_config(cfg_path)
        opened2 = open_library(cfg_path)
        self.assertEqual(len(opened2.decks), 1)
        self.assertTrue(marker.is_file())
