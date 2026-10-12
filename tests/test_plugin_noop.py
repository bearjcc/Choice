# SPDX-License-Identifier: AGPL-3.0-only

import os
import tempfile
import unittest
from pathlib import Path

from choice.act import decide
from choice.open import open_config

FIX = Path(__file__).resolve().parent / "fixtures" / "plugin_host"


class PluginNoopTests(unittest.TestCase):
    def test_decide_accepts_plugin_noop(self):
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
                item_id = "card-a"
                result = decide(deck, item_id, "right", None)
                self.assertTrue(result.get("ok"))
                self.assertTrue(result.get("noop"))
            finally:
                os.environ.pop("CHOICE_DISABLE_WARM", None)


if __name__ == "__main__":
    unittest.main()
