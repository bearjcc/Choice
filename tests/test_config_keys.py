# SPDX-License-Identifier: AGPL-3.0-only

import tempfile
import unittest
from pathlib import Path

from choice.config import ConfigProblem, load_config


class ConfigKeyTests(unittest.TestCase):
    def test_legacy_log_rejected(self):
        tmp = Path(tempfile.mkdtemp())
        path = tmp / "choice.toml"
        path.write_text(
            """
[state]
dir = ".state"

[[sources]]
id = "s"
type = "folder"
path = "."

[[decks]]
id = "d"
title = "D"
source = "s"
mount = "."
legacy_log = "old.events.jsonl"
""".strip(),
            encoding="utf-8",
        )
        with self.assertRaises(ConfigProblem) as ctx:
            load_config(path)
        self.assertIn("legacy_log", str(ctx.exception))
