# SPDX-License-Identifier: AGPL-3.0-only

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_CSS = ROOT / "choice" / "web" / "app.css"


class TopBarLayoutTests(unittest.TestCase):
    def test_title_truncates_and_row_stays_single_line(self):
        text = APP_CSS.read_text(encoding="utf-8")
        self.assertIn(".top-row {", text)
        row_block = text.split(".top-row {", 1)[1].split("}", 1)[0]
        self.assertIn("flex-wrap: nowrap", row_block)
        self.assertIn("min-width: 0", row_block)
        h1_block = text.split(".top h1 {", 1)[1].split("}", 1)[0]
        self.assertIn("text-overflow: ellipsis", h1_block)
        self.assertIn("white-space: nowrap", h1_block)
        self.assertIn("min-width: 0", h1_block)
        self.assertIn(".top-row .count", text)
