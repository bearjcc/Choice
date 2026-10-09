# SPDX-License-Identifier: AGPL-3.0-only

import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from choice.act import decide, progress
from choice.httpd import ChoiceSite
from choice.open import open_config
from choice.open_cache import bust_config, open_library
from choice.swipe_plugin import SwipePlugin

FIX = Path(__file__).resolve().parent / "fixtures" / "plugin_host"


class PluginFixes045Tests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        os.environ["CHOICE_DISABLE_WARM"] = "1"

    def tearDown(self):
        os.environ.pop("CHOICE_DISABLE_WARM", None)
        os.environ.pop("MEDIA_ROW_PATH", None)
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

    def test_pending_page_hides_plugin_decided(self):
        deck = self._deck("plugin_decided_mix")
        deck.load_items()
        snap = progress(deck, pending=True, limit=10, after=None)
        ids = {row["id"] for row in snap["items"]}
        self.assertIn("open-b", ids)
        self.assertNotIn("plug-1", ids)

    def test_cursor_paging_after_decide(self):
        deck = self._deck("hides_decided")
        deck.load_items()
        first = progress(deck, pending=True, limit=1, after=None)
        self.assertEqual(len(first["items"]), 1)
        head = first["items"][0]["id"]
        decide(deck, head, "right", "")
        second = progress(deck, pending=True, limit=1, after=head)
        self.assertEqual(len(second["items"]), 1)
        self.assertNotEqual(second["items"][0]["id"], head)

    def test_repeat_swipe_same_direction_idempotent(self):
        deck = self._deck("hides_decided")
        deck.load_items()
        snap = progress(deck, pending=True, limit=1, after=None)
        item_id = snap["items"][0]["id"]
        first = decide(deck, item_id, "right", "a")
        second = decide(deck, item_id, "right", "b")
        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        self.assertIn("already recorded", second["message"])

    def test_reject_logged(self):
        deck = self._deck("hides_decided")
        deck.load_items()
        decide(deck, "missing-card", "right", "")
        path = deck.state_dir / "rejects.jsonl"
        self.assertTrue(path.is_file())
        self.assertIn("not in the pile", path.read_text(encoding="utf-8"))

    def test_plugin_reload_on_deck_py_change(self):
        cfg = self._config("list_counter")
        opened1 = open_library(cfg)
        first = opened1.decks[0].plugin
        assert isinstance(first, SwipePlugin)
        deck_py = first.folder / "deck.py"
        deck_py.touch()
        opened2 = open_library(cfg)
        self.assertIsNot(opened1, opened2)

    def test_media_bytes_receives_side(self):
        row_path = self.tmp / "media_row.json"
        os.environ["MEDIA_ROW_PATH"] = str(row_path)
        deck = self._deck("media_row")
        plugin = deck.plugin
        assert isinstance(plugin, SwipePlugin)
        plugin.media_bytes("pic", item={"id": "pic"}, side="b")
        payload = json.loads(row_path.read_text(encoding="utf-8"))
        self.assertEqual(payload.get("side"), "b")

    def test_decide_wrong_deck_id_409(self):
        cfg = self._config("hides_decided")
        ChoiceSite.allow_reuse_address = True
        server = ChoiceSite(("127.0.0.1", 0), self.tmp, config_path=cfg)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        try:
            body = json.dumps(
                {"item": "open-1", "direction": "right", "deck_id": "wrong-deck"}
            ).encode("utf-8")
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/decks/d/decide",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                urllib.request.urlopen(req, timeout=10)
                self.fail("expected 409")
            except urllib.error.HTTPError as exc:
                self.assertEqual(exc.code, 409)
        finally:
            server.shutdown()
            bust_config(cfg)


if __name__ == "__main__":
    unittest.main()
