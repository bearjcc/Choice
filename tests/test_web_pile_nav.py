# SPDX-License-Identifier: AGPL-3.0-only

import subprocess
import unittest
from pathlib import Path


class WebPileNavTests(unittest.TestCase):
    def test_pile_nav_node_suite(self):
        root = Path(__file__).resolve().parents[1]
        proc = subprocess.run(
            ["node", "--test", str(root / "tests/web/pile_nav.test.mjs")],
            cwd=root,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
