# SPDX-License-Identifier: AGPL-3.0-only

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from choice.folder_index import scan_incremental
from choice.load import resolve


class ScanCacheBustTests(unittest.TestCase):
    def test_scan_incremental_busts_item_cache(self):
        with tempfile.TemporaryDirectory() as tmpname:
            tmp = Path(tmpname)
            (tmp / "deck.json").write_text(
                json.dumps(
                    {
                        "source": {
                            "type": "images",
                            "path": ".",
                            "recursive": False,
                            "output": "results",
                        },
                        "directions": {"right": {"label": "Yes", "value": "yes"}},
                    }
                ),
                encoding="utf-8",
            )
            (tmp / "solo.jpg").write_bytes(b"x")
            deck = resolve(tmp).decks[0]
            scan_incremental(deck)
            (tmp / "added.jpg").write_bytes(b"y")
            with patch("choice.deck_cache.bust") as bust:
                scan_incremental(deck)
            bust.assert_called()
