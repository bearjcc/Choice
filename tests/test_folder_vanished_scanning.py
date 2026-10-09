# SPDX-License-Identifier: AGPL-3.0-only

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from choice.act import progress
from choice.folder_index import load_index, save_index, scan_incremental
from choice.load import resolve


class FolderVanishedScanningTests(unittest.TestCase):
    def test_missing_files_return_scanning_until_rescan(self):
        with tempfile.TemporaryDirectory() as tmpname:
            tmp = Path(tmpname)
            (tmp / "deck.json").write_text(
                json.dumps(
                    {
                        "source": {
                            "type": "images",
                            "path": ".",
                            "recursive": True,
                            "output": "results",
                        },
                        "directions": {"right": {"label": "Yes", "value": "yes"}},
                    }
                ),
                encoding="utf-8",
            )
            (tmp / "a.jpg").write_bytes(b"x")
            deck = resolve(tmp).decks[0]
            scan_incremental(deck)
            (tmp / "a.jpg").unlink()
            idx = load_index(deck.state_dir)
            idx.stale = True
            save_index(deck.state_dir, idx)
            with patch("choice.folder_index.kick_background_scan") as kicked:
                snap = progress(deck, pending=True, limit=200)
            kicked.assert_called()
            self.assertTrue(snap.get("scanning"))
            self.assertEqual(snap.get("items"), [])
