# SPDX-License-Identifier: AGPL-3.0-only

import os
import tempfile
import time
import unittest
from pathlib import Path

from choice.state_cleanup import cleanup_atomic_tmp_in, pid_alive


class StateCleanupTests(unittest.TestCase):
    def test_pid_alive_current(self):
        self.assertTrue(pid_alive(os.getpid()))

    def test_removes_stale_tmp_for_dead_pid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stale = root / "list_counts.json.999999.tmp"
            stale.write_text("partial", encoding="utf-8")
            removed = cleanup_atomic_tmp_in(root, now=time.time())
            self.assertIn(stale, removed)
            self.assertFalse(stale.exists())

    def test_keeps_young_tmp_for_live_pid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            live = root / f"list_counts.json.{os.getpid()}.tmp"
            live.write_text("writing", encoding="utf-8")
            removed = cleanup_atomic_tmp_in(root, now=time.time())
            self.assertEqual(removed, [])
            self.assertTrue(live.is_file())

    def test_removes_old_tmp_even_for_live_pid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = root / f"list_counts.json.{os.getpid()}.tmp"
            old.write_text("stale", encoding="utf-8")
            ancient = time.time() - 700
            os.utime(old, (ancient, ancient))
            removed = cleanup_atomic_tmp_in(root, now=time.time())
            self.assertIn(old, removed)


if __name__ == "__main__":
    unittest.main()
