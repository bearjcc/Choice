# SPDX-License-Identifier: AGPL-3.0-only

import tomllib
import unittest
from pathlib import Path

import choice


class VersionTests(unittest.TestCase):
    def test_pyproject_matches_package(self):
        root = Path(__file__).resolve().parents[1]
        with root.joinpath("pyproject.toml").open("rb") as fh:
            data = tomllib.load(fh)
        self.assertEqual(data["project"]["version"], choice.__version__)
