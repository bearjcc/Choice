# SPDX-License-Identifier: AGPL-3.0-only

import logging
import os
import tempfile
import unittest
from pathlib import Path

from choice.act import decide, progress
from choice.open import open_config
from choice.sources.swipe import ensure_swipe_directions

FIX = Path(__file__).resolve().parent / "fixtures" / "plugin_host"
ROOT = Path(__file__).resolve().parents[1]


class PluginDirectionsFallbackTests(unittest.TestCase):
    def _config(self, mount: str):
        return f"""
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
mount = "{mount}"
""".strip()

    def _deck(self, mount: str):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "choice.toml"
            cfg.write_text(self._config(mount), encoding="utf-8")
            os.environ["CHOICE_DISABLE_WARM"] = "1"
            try:
                yield open_config(cfg).decks[0]
            finally:
                os.environ.pop("CHOICE_DISABLE_WARM", None)

    def test_no_directions_gets_defaults(self):
        for deck in self._deck("no_directions"):
            self.assertIn("left", deck.directions)
            self.assertIn("right", deck.directions)
            self.assertEqual(deck.directions["left"].label, "No")
            self.assertEqual(deck.directions["right"].label, "Yes")
            meta = deck.public_meta()
            ids = [row["id"] for row in meta["directions"]]
            self.assertIn("left", ids)
            self.assertIn("right", ids)

    def test_empty_directions_gets_defaults(self):
        for deck in self._deck("empty_directions"):
            self.assertIn("left", deck.directions)
            self.assertIn("right", deck.directions)

    def test_malformed_directions_gets_defaults(self):
        for deck in self._deck("malformed_directions"):
            self.assertIn("left", deck.directions)
            self.assertIn("right", deck.directions)

    def test_immich_cleanup_like_decide(self):
        for deck in self._deck("immich_cleanup_like"):
            items, _ = deck.load_items()
            self.assertIn("left", deck.directions)
            snap = progress(deck, pending=True, limit=10, offset=0)
            item_id = snap["items"][0]["id"]
            out = decide(deck, item_id, "right", None)
            self.assertTrue(out.get("ok"))

    def test_ensure_swipe_directions_logs_warning(self):
        with self.assertLogs("choice.sources.swipe", level="WARNING") as captured:
            ensure_swipe_directions({}, deck_id="x", mount="y")
        self.assertTrue(any("missing or invalid" in line for line in captured.output))


class PluginDirectionsClientTests(unittest.TestCase):
    def test_client_payload_direction_fallback(self):
        text = (ROOT / "choice" / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("DEFAULT_DIRECTIONS", text)
        self.assertIn("payloadDirections", text)
        self.assertIn('offered != null && String(offered).trim() !== ""', text)


if __name__ == "__main__":
    unittest.main()
