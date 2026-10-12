# SPDX-License-Identifier: AGPL-3.0-only

import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path

from choice.act import progress
from choice.folder_index import load_index, scan_incremental
from choice.load import resolve


class ScanMaxWaitTests(unittest.TestCase):
    def test_poll_during_changes_sees_updates_within_six_seconds(self):
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
            (tmp / "keep").mkdir()
            incoming = tmp / "incoming"
            incoming.mkdir()
            (incoming / "solo.jpg").write_bytes(b"x")
            deck = resolve(tmp).decks[0]
            scan_incremental(deck)
            stop = threading.Event()
            seen: set[str] = set()

            def poll() -> None:
                while not stop.is_set():
                    snap = progress(deck, pending=True, limit=200, after=None)
                    for row in snap.get("items") or []:
                        seen.add(row["id"])
                    time.sleep(0.3)

            poller = threading.Thread(target=poll, daemon=True)
            poller.start()
            batch = incoming / "batch"
            batch.mkdir()
            (batch / "new.jpg").write_bytes(b"y")
            deadline = time.monotonic() + 6.0
            while time.monotonic() < deadline:
                if "incoming/batch/new.jpg" in seen:
                    break
                time.sleep(0.1)
            self.assertIn("incoming/batch/new.jpg", seen)
            shutil.rmtree(batch)
            deadline = time.monotonic() + 6.0
            while time.monotonic() < deadline:
                idx = load_index(deck.state_dir)
                if "incoming/batch/new.jpg" not in idx.ordered:
                    break
                time.sleep(0.1)
            idx = load_index(deck.state_dir)
            self.assertNotIn("incoming/batch/new.jpg", idx.ordered)
            stop.set()
            poller.join(timeout=2.0)
            from choice.work_queue import wait_idle

            wait_idle(deck.state_dir, timeout=60.0)
            time.sleep(0.5 if os.name == "nt" else 0.25)


if __name__ == "__main__":
    unittest.main()
