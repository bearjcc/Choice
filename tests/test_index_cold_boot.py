# SPDX-License-Identifier: AGPL-3.0-only

"""Cold library index must stay fast and must not sync-call list_items."""

import json
import os
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

from choice.act import index_summary
from choice.deck_index import clear_index
from choice.httpd import ChoiceSite
from choice.open import open_config

FIX = Path(__file__).resolve().parent / "fixtures" / "plugin_host"


class IndexColdBootTests(unittest.TestCase):
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
mount = "slow_list"
""".strip(),
            encoding="utf-8",
        )
        return cfg

    def test_index_summary_uses_total_without_sync_list_items(self):
        deck = open_config(self._config()).decks[0]
        counts = deck.state_dir / "list_counts.json"
        counts.parent.mkdir(parents=True, exist_ok=True)
        counts.write_text(
            json.dumps({"total": 12, "plugin_decided": ["a"]}),
            encoding="utf-8",
        )
        clear_index(deck)
        with mock.patch.object(deck, "load_items", side_effect=AssertionError("sync list_items")):
            start = time.perf_counter()
            home = index_summary(deck)
            elapsed = time.perf_counter() - start
        self.assertTrue(home.get("ok"))
        self.assertEqual(home["total"], 12)
        self.assertLess(elapsed, 0.12)

    def test_http_index_returns_before_slow_list_items(self):
        cfg = self._config()
        deck = open_config(cfg).decks[0]
        counts = deck.state_dir / "list_counts.json"
        counts.write_text(json.dumps({"total": 4, "plugin_decided": []}), encoding="utf-8")
        ChoiceSite.allow_reuse_address = True
        server = ChoiceSite(("127.0.0.1", 0), self.tmp, config_path=cfg)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        try:
            start = time.perf_counter()
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/index", timeout=5
            ) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            elapsed = time.perf_counter() - start
            self.assertEqual(resp.status, 200)
            self.assertTrue(body.get("ok"))
            decks = body.get("decks") or []
            self.assertEqual(len(decks), 1)
            self.assertEqual(decks[0].get("total"), 4)
            self.assertLess(elapsed, 0.75, f"/api/index took {elapsed:.2f}s")
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
