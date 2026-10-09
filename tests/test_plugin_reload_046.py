# SPDX-License-Identifier: AGPL-3.0-only

import json
import os
import shutil
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

from choice.httpd import ChoiceSite
from choice.open_cache import open_library, reload_library

FIX = Path(__file__).resolve().parent / "fixtures" / "plugin_host" / "hides_decided"


class PluginReload046Tests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.mount = self.tmp / "mount"
        shutil.copytree(FIX, self.mount)
        os.environ["CHOICE_DISABLE_WARM"] = "1"
        self.cfg = self.tmp / "choice.toml"
        self.cfg.write_text(
            f"""
[state]
dir = "state"

[[sources]]
id = "swipe"
type = "swipe"
path = "{self.tmp.as_posix()}"

[[decks]]
id = "d"
title = "D"
source = "swipe"
mount = "mount"
""".strip(),
            encoding="utf-8",
        )

    def tearDown(self):
        os.environ.pop("CHOICE_DISABLE_WARM", None)
        self._tmp.cleanup()

    def _marker_title(self) -> str:
        deck = open_library(self.cfg).decks[0]
        items, _warnings = deck.load_items()
        return items[0].title

    def _write_marker(self, marker: str) -> None:
        deck_py = self.mount / "deck.py"
        text = deck_py.read_text(encoding="utf-8")
        if 'MARKER = "' in text:
            lines = []
            for line in text.splitlines():
                if line.startswith("MARKER = "):
                    lines.append(f'MARKER = "{marker}"')
                else:
                    lines.append(line)
            deck_py.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return
        deck_py.write_text(
            text
            + f'\nMARKER = "{marker}"\n'
            + "def _marker_title():\n"
            + "    return MARKER\n",
            encoding="utf-8",
        )
        # patch list_items return title
        if "MARKER" not in text:
            deck_py.write_text(
                deck_py.read_text(encoding="utf-8").replace(
                    '"One"', '_marker_title() if "MARKER" in globals() else "One"'
                ),
                encoding="utf-8",
            )

    def _setup_marker_deck(self) -> None:
        deck_py = self.mount / "deck.py"
        deck_py.write_text(
            '''
class Deck:
    id = "hides_decided"
    title = "Hides decided"
    directions = {"right": {"label": "Keep"}}
    MARKER = "AAAA"

    def list_items(self, filter=None):
        return [
            {"id": "open-1", "title": self.MARKER},
            {"id": "open-2", "title": "Two"},
            {"id": "open-3", "title": "Three"},
        ]

    def handle(self, item_id, direction, note=None):
        return {"ok": True}
'''.strip()
            + "\n",
            encoding="utf-8",
        )

    def _set_marker(self, marker: str) -> None:
        deck_py = self.mount / "deck.py"
        text = deck_py.read_text(encoding="utf-8")
        import re

        deck_py.write_text(re.sub(r'MARKER = "...."', f'MARKER = "{marker}"', text), encoding="utf-8")

    def test_three_edits_via_reload_immediate(self):
        self._setup_marker_deck()
        for marker in ("AAAA", "BBBB", "CCCC"):
            self._set_marker(marker)
            reload_library(self.cfg)
            self.assertEqual(self._marker_title(), marker)

    def test_auto_reload_within_three_seconds(self):
        self._setup_marker_deck()
        reload_library(self.cfg)
        self.assertEqual(self._marker_title(), "AAAA")
        self._set_marker("BBBB")
        deadline = time.monotonic() + 3.0
        seen = None
        while time.monotonic() < deadline:
            seen = self._marker_title()
            if seen == "BBBB":
                break
            time.sleep(0.05)
        self.assertEqual(seen, "BBBB")

    def test_reload_endpoint_applies_same_size_edit(self):
        self._setup_marker_deck()
        ChoiceSite.allow_reuse_address = True
        server = ChoiceSite(("127.0.0.1", 0), self.tmp, config_path=self.cfg)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        try:
            reload_library(self.cfg)
            self._set_marker("DDDD")
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/reload",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=10)
            title = self._marker_title()
            self.assertEqual(title, "DDDD")
        finally:
            server.shutdown()


if __name__ == "__main__":
    unittest.main()
