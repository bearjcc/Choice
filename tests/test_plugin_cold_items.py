# SPDX-License-Identifier: AGPL-3.0-only

"""Cold /items latency: Choice overhead vs plugin list_items time."""

import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

from choice.act import index_summary
from choice.deck_index import clear_index
from choice.httpd import ChoiceSite
from choice.open import open_config

FIX = Path(__file__).resolve().parent / "fixtures" / "plugin_host"


class PluginColdItemsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        os.environ.pop("CHOICE_DISABLE_WARM", None)
        os.environ["SLOW_LIST_DELAY"] = "0.25"

    def tearDown(self):
        os.environ.pop("SLOW_LIST_DELAY", None)
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

    def test_index_does_not_block_on_full_list(self):
        deck = open_config(self._config()).decks[0]
        clear_index(deck)
        start = time.perf_counter()
        home = index_summary(deck)
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, 0.12, "index_summary should not call list_items on cold home")
        self.assertTrue(home.get("ok"))

    def test_first_items_waits_on_plugin_not_extra_snapshot_work(self):
        cfg = self._config()
        ChoiceSite.allow_reuse_address = True
        server = ChoiceSite(("127.0.0.1", 0), self.tmp, config_path=cfg)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        delay = float(os.environ["SLOW_LIST_DELAY"])
        try:
            start = time.perf_counter()
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/decks/d/items?pending=1&limit=200&w=960",
                timeout=30,
            ) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            elapsed = time.perf_counter() - start
            self.assertEqual(resp.status, 200)
            self.assertTrue(body.get("ok"))
            self.assertGreaterEqual(len(body.get("items") or []), 1)
            # Dominant cost is plugin sleep; Choice adds well under 150ms on top (more on Windows CI).
            overhead = 0.65 if sys.platform == "win32" else 0.35
            self.assertLess(elapsed, delay + overhead, f"elapsed={elapsed:.3f}s plugin_delay={delay}s")
            self.assertGreaterEqual(elapsed, delay * 0.85)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
