# SPDX-License-Identifier: AGPL-3.0-only

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_CSS = ROOT / "choice" / "web" / "app.css"

# Block covering filter flyout UI (panel through sort control).
_FILTER_BLOCK_START = ".filter-panel {"
_FILTER_BLOCK_END = ".filter-group {"


class FilterPanelThemeTests(unittest.TestCase):
    def _filter_css_block(self) -> str:
        text = APP_CSS.read_text(encoding="utf-8")
        start = text.index(_FILTER_BLOCK_START)
        end = text.index(_FILTER_BLOCK_END, start)
        return text[start:end]

    def test_no_hardcoded_white_in_filter_panel_styles(self):
        block = self._filter_css_block()
        lowered = block.lower()
        self.assertNotIn("#fff", lowered)
        self.assertNotIn("#ffffff", lowered)
        self.assertNotRegex(block, r"\bwhite\b")

    def test_filter_panel_uses_semantic_tokens(self):
        block = self._filter_css_block()
        required = (
            "var(--card)",
            "var(--text)",
            "var(--line)",
            "var(--fill)",
            "var(--muted)",
        )
        for token in required:
            self.assertIn(token, block, f"filter panel CSS should reference {token}")

    def test_filter_panel_inner_sets_color_scheme(self):
        block = self._filter_css_block()
        self.assertRegex(
            block,
            r"\.filter-panel-inner\s*\{[^}]*color-scheme:\s*light\s+dark",
            re.DOTALL,
        )
