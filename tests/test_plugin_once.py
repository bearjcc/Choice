# SPDX-License-Identifier: AGPL-3.0-only

import os
import tempfile
import unittest
from pathlib import Path

from choice.act import decide
from choice.open import open_config


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
