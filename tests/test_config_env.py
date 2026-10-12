# SPDX-License-Identifier: AGPL-3.0-only

import os
import tempfile
import unittest
from pathlib import Path

from choice.config import load_config


class ConfigEnvTests(unittest.TestCase):
    def test_choice_state_dir_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg_path = root / "choice.toml"
            cfg_path.write_text(
                """
[state]
dir = "state"

[[sources]]
id = "s"
type = "folder"
path = "."

[[decks]]
id = "d"
title = "D"
source = "s"
mount = "."
""".strip(),
                encoding="utf-8",
            )
            os.environ["CHOICE_STATE_DIR"] = str(root / "override-state")
            try:
                cfg = load_config(cfg_path)
                self.assertEqual(
                    cfg.state_dir.resolve(),
                    (root / "override-state").resolve(),
                )
            finally:
                os.environ.pop("CHOICE_STATE_DIR", None)


if __name__ == "__main__":
    unittest.main()
