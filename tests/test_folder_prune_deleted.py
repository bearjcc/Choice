# SPDX-License-Identifier: AGPL-3.0-only

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from choice.act import decide, index_summary
from choice.folder_index import load_index, scan_incremental
from choice.load import resolve


class FolderPruneDeletedTests(unittest.TestCase):
    def test_deleted_subtree_prunes_index_and_counts(self):
        with tempfile.TemporaryDirectory() as tmpname:
            tmp = Path(tmpname)
            for name in ("keep", "reject"):
                (tmp / name).mkdir()
            incoming = tmp / "incoming"
            incoming.mkdir()
            for i in range(5):
                (incoming / f"a{i}.jpg").write_bytes(b"x")
            batch = incoming / "batch"
            batch.mkdir()
            for i in range(8):
                (batch / f"b{i}.jpg").write_bytes(b"x")
            (tmp / "deck.json").write_text(
                json.dumps(
                    {
                        "source": {
                            "type": "images",
                            "path": ".",
                            "recursive": True,
                            "output": "sort",
                            "sort": {"right": "keep", "left": "reject"},
                        },
                        "directions": {
                            "right": {"label": "Keep", "value": "keep"},
                            "left": {"label": "Reject", "value": "reject"},
                        },
                    }
                ),
                encoding="utf-8",
            )
            deck = resolve(tmp).decks[0]
            scan_incremental(deck)
            decide(deck, "incoming/a0.jpg", "right", None)
            shutil.rmtree(batch)
            scan_incremental(deck)
            idx = load_index(deck.state_dir)
            self.assertFalse(any(p.startswith("incoming/batch/") for p in idx.ordered))
            snap = index_summary(deck)
            self.assertEqual(snap["total"], snap["decided"] + snap["left"])


if __name__ == "__main__":
    unittest.main()
