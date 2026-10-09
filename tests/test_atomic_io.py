# SPDX-License-Identifier: AGPL-3.0-only

import errno
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from choice.atomic_io import atomic_replace


class AtomicReplaceTests(unittest.TestCase):
    def test_retries_sharing_violation(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "out.json"
            tmpf = Path(tmp) / "out.tmp"
            tmpf.write_text("{}", encoding="utf-8")
            calls = {"n": 0}

            real_replace = os.replace

            def flaky_replace(src, dst):
                calls["n"] += 1
                if calls["n"] < 3:
                    raise OSError(errno.EACCES, "locked", str(dst))
                return real_replace(src, dst)

            with mock.patch("choice.atomic_io.os.replace", side_effect=flaky_replace):
                atomic_replace(tmpf, dest)
            self.assertEqual(calls["n"], 3)
            self.assertTrue(dest.is_file())
