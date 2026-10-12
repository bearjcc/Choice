# SPDX-License-Identifier: AGPL-3.0-only

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class FilterChangeClientTests(unittest.TestCase):
    def test_filter_change_flushes_buffer_and_blocks_decide(self):
        text = (ROOT / "choice" / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("state.filterFlushing", text)
        self.assertIn("filterFlushing) return", text)
        self.assertIn("++state.itemsLoadSeq", text)
        self.assertIn("filterEpoch", text)


if __name__ == "__main__":
    unittest.main()
