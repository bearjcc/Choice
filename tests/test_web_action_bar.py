# SPDX-License-Identifier: AGPL-3.0-only

import os
import subprocess
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from choice.httpd import ChoiceSite
from choice.open import open_config

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "action_bar"
CONFIG = FIX / "action_bar.toml"


class SortDirectionIconTests(unittest.TestCase):
    def test_sort_icon_keys_in_config(self):
        deck = open_config(CONFIG).decks[1]
        self.assertEqual(deck.directions["right"].icon, "star")
        self.assertEqual(deck.directions["left"].icon, "trash")
        meta = deck.public_meta()
        icons = {row["id"]: row.get("icon") for row in meta["directions"]}
        self.assertEqual(icons.get("right"), "star")
        self.assertEqual(icons.get("left"), "trash")


class WebActionBarTests(unittest.TestCase):
    def setUp(self):
        os.environ["CHOICE_DISABLE_WARM"] = "1"
        ChoiceSite.allow_reuse_address = True
        self.server = ChoiceSite(("127.0.0.1", 0), FIX, config_path=CONFIG)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]
        self.base_url = f"http://127.0.0.1:{self.port}/?testhooks=1"
        for _ in range(40):
            try:
                urllib.request.urlopen(
                    f"http://127.0.0.1:{self.port}/api/health",
                    timeout=0.25,
                )
                break
            except (urllib.error.URLError, TimeoutError):
                time.sleep(0.05)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        os.environ.pop("CHOICE_DISABLE_WARM", None)

    def test_action_bar_playwright(self):
        web_pkg = ROOT / "tests" / "web" / "node_modules" / "playwright"
        if not web_pkg.is_dir():
            subprocess.run(
                ["npm", "install", "--no-save", "playwright@1.49.1"],
                cwd=ROOT / "tests" / "web",
                check=True,
                capture_output=True,
                text=True,
            )
        proc = subprocess.run(
            ["node", str(ROOT / "tests/web/action_bar_playwright.mjs"), self.base_url],
            cwd=ROOT,
            capture_output=True,
            text=True,
            env=os.environ.copy(),
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
