# SPDX-License-Identifier: AGPL-3.0-only

import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from choice.folder_index import apply_move, load_index, readmit_path, scan_incremental
from choice.load import resolve


class ReadmitIdempotentTests(unittest.TestCase):
    def test_concurrent_readmit_and_apply_move_no_duplicates(self):
        with tempfile.TemporaryDirectory() as tmpname:
            tmp = Path(tmpname)
            (tmp / "deck.json").write_text(
                json.dumps(
                    {
                        "source": {
                            "type": "images",
                            "path": ".",
                            "recursive": True,
                            "output": "sort",
                            "sort": {"right": "keep"},
                        },
                        "directions": {"right": {"label": "Keep", "value": "keep"}},
                    }
                ),
                encoding="utf-8",
            )
            rel = "incoming/a.jpg"
            (tmp / "incoming").mkdir()
            (tmp / rel).write_bytes(b"x")
            (tmp / "keep").mkdir()
            deck = resolve(tmp).decks[0]
            scan_incremental(deck)
            state = deck.state_dir

            def readmit() -> None:
                readmit_path(state, rel, deck=deck)

            def remove() -> None:
                apply_move(state, rel, "keep/a.jpg", deck=deck)

            with ThreadPoolExecutor(max_workers=16) as pool:
                futures = []
                for _ in range(40):
                    futures.append(pool.submit(readmit))
                    futures.append(pool.submit(remove))
                for fut in as_completed(futures):
                    fut.result()

            idx = load_index(state)
            self.assertEqual(len(idx.ordered), len(set(idx.ordered)))
            self.assertNotIn(rel, idx.ordered)


if __name__ == "__main__":
    unittest.main()
