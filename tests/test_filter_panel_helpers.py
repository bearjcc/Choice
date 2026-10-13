# SPDX-License-Identifier: AGPL-3.0-only

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class FilterPanelHelperTests(unittest.TestCase):
    def test_filter_panel_helpers_node(self):
        script = ROOT / "tests" / "web" / "filter_panel_unit.mjs"
        proc = subprocess.run(
            ["node", str(script)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
