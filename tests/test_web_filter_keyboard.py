# SPDX-License-Identifier: AGPL-3.0-only

import json
import os
import subprocess
import threading
import unittest
from pathlib import Path

from choice.httpd import ChoiceSite

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "filter_flyout"
CONFIG = FIX / "filter_flyout.toml"
SHOT_DIR = ROOT / "tests" / "artifacts" / "filter_keyboard"


class WebFilterKeyboardTests(unittest.TestCase):
    def setUp(self):
        os.environ["CHOICE_DISABLE_WARM"] = "1"
        self._users = FIX / ".choice" / "users.json"
        self._users.parent.mkdir(parents=True, exist_ok=True)
        self._users.write_text(
            json.dumps({"users": [{"id": "bear", "name": "Bear", "decks": "*"}]}),
            encoding="utf-8",
        )
        ChoiceSite.allow_reuse_address = True
        self.server = ChoiceSite(("127.0.0.1", 0), FIX, config_path=CONFIG)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]
        self.base_url = f"http://127.0.0.1:{self.port}/?testhooks=1"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        os.environ.pop("CHOICE_DISABLE_WARM", None)

    def test_filter_viewport_acceptance_helper(self):
        proc = subprocess.run(
            ["node", "--test", str(ROOT / "tests/web/filter_panel_viewport.test.mjs")],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_viewport_sync_script_served(self):
        import urllib.request

        with urllib.request.urlopen(
            f"http://127.0.0.1:{self.port}/viewport_sync.js", timeout=10
        ) as resp:
            body = resp.read().decode("utf-8")
        self.assertIn("ChoiceVisualViewport", body)
        self.assertIn("--vv-h", body)

    @unittest.skipUnless(
        os.environ.get("CHOICE_RUN_PLAYWRIGHT"),
        "optional; set CHOICE_RUN_PLAYWRIGHT=1 with Playwright browsers installed",
    )
    def test_filter_keyboard_playwright(self):
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
            [
                "node",
                str(ROOT / "tests/web/filter_keyboard_playwright.mjs"),
                self.base_url,
                str(SHOT_DIR),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            env=os.environ.copy(),
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
