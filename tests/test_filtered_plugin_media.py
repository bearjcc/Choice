# SPDX-License-Identifier: AGPL-3.0-only

import json
import os
import tempfile
import threading
import time
import unittest
import urllib.parse
import urllib.request
from pathlib import Path

from choice.deck_cache import load_items as cached_load_items
from choice.deck_index import clear_index, list_generation, record_items
from choice.httpd import ChoiceSite
from choice.load import Item
from choice.open import open_config
from choice.plugin_filters import encode_filter_param, reset_request_filter, set_request_filter

FIX = Path(__file__).resolve().parent / "fixtures" / "plugin_host"


class FilteredPluginMediaTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        os.environ["CHOICE_DISABLE_WARM"] = "1"

    def tearDown(self):
        os.environ.pop("CHOICE_DISABLE_WARM", None)
        self._tmp.cleanup()

    def _config(self) -> Path:
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
mount = "filter_media"
""".strip(),
            encoding="utf-8",
        )
        return cfg

    def test_media_and_decide_honor_filter_param(self):
        cfg = self._config()
        ChoiceSite.allow_reuse_address = True
        server = ChoiceSite(("127.0.0.1", 0), self.tmp, config_path=cfg)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        f = encode_filter_param({"tag": {"values": ["a"]}})
        base = f"http://127.0.0.1:{port}"
        try:
            with urllib.request.urlopen(
                f"{base}/api/decks/d/items?pending=1&limit=5&f={urllib.parse.quote(f)}",
                timeout=10,
            ) as resp:
                items = json.loads(resp.read().decode("utf-8"))
            self.assertEqual([row["id"] for row in items.get("items") or []], ["filtered-card"])
            media_url = (
                f"{base}/api/decks/d/media?item=filtered-card&v=t1&f={urllib.parse.quote(f)}"
            )
            with urllib.request.urlopen(media_url, timeout=10) as resp:
                self.assertEqual(resp.status, 200)
                self.assertTrue(resp.headers.get("Content-Type", "").startswith("image/"))
            decide_body = json.dumps(
                {"item": "filtered-card", "direction": "right", "deck_id": "d"}
            ).encode("utf-8")
            req = urllib.request.Request(
                f"{base}/api/decks/d/decide?f={urllib.parse.quote(f)}",
                data=decide_body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(body.get("ok"))
        finally:
            server.shutdown()
            server.server_close()

    def test_plugin_cache_stamp_bumps_when_list_changes(self):
        deck = open_config(self._config()).decks[0]
        clear_index(deck)
        token = set_request_filter({"tag": {"values": ["a"]}})
        try:
            gen0 = list_generation(deck)
            cached_load_items(deck)
            gen1 = list_generation(deck)
            self.assertGreater(gen1, gen0)
            record_items(
                deck,
                [
                    Item(
                        id="filtered-card",
                        kind="card",
                        title="T",
                        body="",
                        fields={},
                    )
                ],
            )
            gen2 = list_generation(deck)
            self.assertGreater(gen2, gen1)
            from choice.deck_cache import _stamp

            stamp_a = _stamp(deck, json.dumps({"tag": {"values": ["a"]}}, sort_keys=True))
            time.sleep(0.01)
            record_items(
                deck,
                [
                    Item(
                        id="other",
                        kind="card",
                        title="O",
                        body="",
                        fields={},
                    )
                ],
            )
            stamp_b = _stamp(deck, json.dumps({"tag": {"values": ["a"]}}, sort_keys=True))
            self.assertNotEqual(stamp_a, stamp_b)
        finally:
            reset_request_filter(token)


if __name__ == "__main__":
    unittest.main()
