# SPDX-License-Identifier: AGPL-3.0-only

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class UndoInstantClientTests(unittest.TestCase):
    def test_app_wires_instant_undo(self):
        text = (ROOT / "choice" / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("reconcileAfterUndo", text)
        self.assertIn("DECIDE_HISTORY_MAX", text)
        self.assertIn("state.undoInFlight", text)
        self.assertIn("resolvedMediaSrc", text)
        self.assertNotIn(
            "setStatus(data.message || \"\");\n  const ok = await loadItems();\n  if (ok) renderDeck();",
            text,
        )


if __name__ == "__main__":
    unittest.main()
