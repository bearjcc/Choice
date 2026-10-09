# SPDX-License-Identifier: AGPL-3.0-only

import tempfile
import unittest
from pathlib import Path

from choice.load import Deck
from choice.work_queue import enqueue_file_op


class WorkQueueTests(unittest.TestCase):
    def test_enqueue_runs_inline_under_sync_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / ".choice"
            state.mkdir()
            src = root / "a.jpg"
            src.write_bytes(b"x")
            dest_dir = root / "keep"
            dest_dir.mkdir()
            deck = Deck(
                id="d",
                title="D",
                root=root,
                state_dir=state,
                directions={},
                buttons=[],
                blind=False,
                warnings=[],
                folder_scan=None,
                _load=lambda: ([], []),
            )
            op = {"op": "move", "from": "a.jpg", "to": "keep/a.jpg"}
            enqueue_file_op(deck, "dec-1", op)
            from choice.work_queue import wait_idle

            wait_idle(state, timeout=30.0)
            self.assertFalse(src.is_file())
            self.assertTrue((dest_dir / "a.jpg").is_file())
            from choice.work_queue import snapshot_for

            snap = snapshot_for(deck)
            self.assertEqual(snap.pending, 0)
            self.assertEqual(snap.running, 0)
