# SPDX-License-Identifier: AGPL-3.0-only

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from choice.state_cleanup import cleanup_atomic_tmp_in, pid_alive


class StateCleanupTests(unittest.TestCase):
    def test_pid_alive_current(self):
        self.assertTrue(pid_alive(os.getpid()))

    def test_keeps_young_tmp_without_pid_probe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            young = root / "list_counts.json.999999.tmp"
            young.write_text("partial", encoding="utf-8")
            with mock.patch("choice.state_cleanup.pid_alive") as probe:
                removed = cleanup_atomic_tmp_in(root, now=time.time())
                probe.assert_not_called()
            self.assertEqual(removed, [])
            self.assertTrue(young.is_file())

    def test_removes_stale_tmp_for_dead_pid_after_probe_age(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stale = root / "list_counts.json.999999.tmp"
            stale.write_text("partial", encoding="utf-8")
            aged = time.time() - 35
            os.utime(stale, (aged, aged))
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

    def test_removes_mkstemp_style_tmp_when_old(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stale = root / "folder_index.json.42.99.a1b2c3.tmp"
            stale.write_text("partial", encoding="utf-8")
            ancient = time.time() - 700
            os.utime(stale, (ancient, ancient))
            removed = cleanup_atomic_tmp_in(root, now=time.time())
            self.assertIn(stale, removed)

    def test_windows_pid_alive_uses_exit_code(self):
        if sys.platform == "win32":
            self.assertTrue(pid_alive(os.getpid()))
            return
        with mock.patch("choice.state_cleanup.sys.platform", "win32"):
            with mock.patch("choice.state_cleanup._pid_alive_windows", return_value=False) as probe:
                self.assertFalse(pid_alive(4242))
                probe.assert_called_once_with(4242)


if __name__ == "__main__":
    unittest.main()
