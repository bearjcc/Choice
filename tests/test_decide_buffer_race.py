# SPDX-License-Identifier: AGPL-3.0-only

"""Reorder while the client holds ids must not reshuffle the visible head."""

import json
import os
import tempfile
import threading
import time
import unittest
import urllib.parse
import urllib.request
from pathlib import Path

from choice.act import decide, progress
from choice.httpd import ChoiceSite
from choice.open import open_config

FIX = Path(__file__).resolve().parent / "fixtures" / "plugin_host"


class DecideBufferRaceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        os.environ["CHOICE_DISABLE_WARM"] = "1"

    def tearDown(self):
        os.environ.pop("CHOICE_DISABLE_WARM", None)
        self._tmp.cleanup()

    def _plugin_config(self, mount: str) -> Path:
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

    def test_held_pile_survives_plugin_reorder(self):
        from choice.deck_index import clear_index

        deck = open_config(self._plugin_config("reorder_list")).decks[0]
        deck.load_items()
        first = progress(deck, pending=True, limit=10)
        ids = [row["id"] for row in first["items"]]
        self.assertGreaterEqual(len(ids), 3)
        held = ids[:2]
        clear_index(deck)
        deck.load_items()
        again = progress(deck, pending=True, limit=10, held=held)
        page_ids = [row["id"] for row in again["items"]]
        self.assertEqual(page_ids[:2], held)

    def test_decide_targets_shown_id_after_reorder(self):
        cfg = self._plugin_config("reorder_list")
        deck = open_config(cfg).decks[0]
        deck.load_items()
        snap = progress(deck, pending=True, limit=5)
        target = snap["items"][0]
        item_id = target["id"]
        held = [item_id]
        progress(deck, pending=True, limit=5, held=held)
        result = decide(deck, item_id, "right", None)
        self.assertTrue(result.get("ok"))

    def test_http_decide_while_items_reorder(self):
        cfg = self._plugin_config("reorder_list")
        ChoiceSite.allow_reuse_address = True
        server = ChoiceSite(("127.0.0.1", 0), self.tmp, config_path=cfg, client_buffer_size=30)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/decks/d/items?pending=1&limit=5", timeout=10
            ) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            item_id = body["items"][0]["id"]
            held = urllib.parse.quote(",".join(row["id"] for row in body["items"][:2]))
            decide_body = json.dumps(
                {"item": item_id, "direction": "right", "deck_id": "d"}
            ).encode("utf-8")
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/decks/d/decide",
                data=decide_body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                decided = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(decided.get("ok"))
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/decks/d/items?pending=1&limit=5&held={held}",
                timeout=10,
            ) as resp:
                after = json.loads(resp.read().decode("utf-8"))
            after_ids = [row["id"] for row in after.get("items") or []]
            self.assertNotEqual(after_ids[0], item_id)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
