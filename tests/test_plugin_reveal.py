# SPDX-License-Identifier: AGPL-3.0-only

import os
import tempfile
import unittest
from pathlib import Path

from choice.act import decide, progress
from choice.load import reveal_visible_in_api, swipe_item_public
from choice.open import open_config
from choice.swipe_plugin import SwipePlugin, _parse_reveal, load_swipe_class, swipe_item_to_choice

FIX = Path(__file__).resolve().parent / "fixtures" / "plugin_host"
ROOT = Path(__file__).resolve().parents[1]


class PluginRevealTests(unittest.TestCase):
    def _deck(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "choice.toml"
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
mount = "plugin_reveal"
""".strip(),
                encoding="utf-8",
            )
            os.environ["CHOICE_DISABLE_WARM"] = "1"
            try:
                yield open_config(cfg).decks[0]
            finally:
                os.environ.pop("CHOICE_DISABLE_WARM", None)

    def test_parse_reveal_dict(self):
        rows = _parse_reveal({"reveal": {"real": "A", "A_model": "x"}})
        self.assertEqual(dict(rows), {"real": "A", "A_model": "x"})

    def _plugin(self, mount: str) -> SwipePlugin:
        folder = FIX / mount
        return SwipePlugin(
            obj=load_swipe_class(folder / "deck.py", folder.name),
            folder=folder,
            deck_id="t",
            title="T",
        )

    def test_swipe_item_stores_reveal(self):
        plugin = self._plugin("plugin_reveal")
        row = {
            "id": "x",
            "ab": {"a": {"text": "a"}, "b": {"text": "b"}},
            "reveal": {"real": "A"},
        }
        item, _ = swipe_item_to_choice(row, FIX / "plugin_reveal", plugin)
        self.assertEqual(item.reveal[0], ("real", "A"))

    def test_items_omit_reveal_until_decided(self):
        for deck in self._deck():
            deck.load_items()
            pending = progress(deck, pending=True, limit=10, offset=0)
            self.assertEqual(len(pending["items"]), 2)
            self.assertNotIn("reveal", pending["items"][0])
            self.assertNotIn("reveal", pending["items"][1])
            out = decide(deck, "pair-1", "left", None)
            self.assertTrue(out.get("ok"))
            self.assertIn("reveal", out)
            self.assertEqual(out["reveal"][0]["label"], "real")
            still_pending = progress(deck, pending=True, limit=10, offset=0)
            for row in still_pending["items"]:
                self.assertNotIn("reveal", row)
            review = progress(deck, pending=False, limit=10, offset=0)
            first = next(r for r in review["items"] if r["id"] == "pair-1")
            self.assertIn("reveal", first)
            self.assertNotIn("reveal", next(r for r in review["items"] if r["id"] == "pair-2"))

    def test_swipe_item_public_gates_reveal(self):
        plugin = self._plugin("plugin_reveal")
        row = {
            "id": "x",
            "ab": {"a": {"text": "a"}, "b": {"text": "b"}},
            "reveal": {"real": "A"},
        }
        item, _ = swipe_item_to_choice(row, FIX / "plugin_reveal", plugin)
        deck = type("D", (), {"show_filename": False})()
        hidden = swipe_item_public(deck, item, None, choice_row=None)
        self.assertNotIn("reveal", hidden)
        shown = swipe_item_public(
            deck,
            item,
            "A",
            choice_row={"value": "A", "label": "A", "later": False},
        )
        self.assertIn("reveal", shown)

    def test_reveal_not_shown_for_skip(self):
        self.assertFalse(reveal_visible_in_api({"later": True, "value": "skip"}))

    def test_client_reveal_helpers(self):
        text = (ROOT / "choice" / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("appendReveal", text)
        self.assertIn("applyDecidePayload", text)
        self.assertIn("itemDecided", text)


if __name__ == "__main__":
    unittest.main()
