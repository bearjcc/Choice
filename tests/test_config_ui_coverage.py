# SPDX-License-Identifier: AGPL-3.0-only

import unittest
from pathlib import Path

from choice.config_schema import (
    NOT_EXPOSED,
    ui_exposed_keys,
    validate_registry_complete,
    validate_ui_coverage,
)

ROOT = Path(__file__).resolve().parents[1]
UI_JS = [
    ROOT / "choice/web/server_admin.js",
    ROOT / "choice/web/config_ui.js",
    ROOT / "choice/web/app.js",
]


class ConfigUiCoverageTests(unittest.TestCase):
    def test_every_exposed_key_has_ui_marker(self):
        js = "\n".join(path.read_text(encoding="utf-8") for path in UI_JS)
        missing = validate_ui_coverage(js)
        self.assertEqual(
            missing,
            [],
            "Add data-config-key to admin/deck UI or NOT_EXPOSED in config_schema.py: "
            + ", ".join(missing),
        )

    def test_loader_keys_accounted_for(self):
        orphan = validate_registry_complete()
        self.assertEqual(orphan, [], f"Unaccounted config keys: {orphan}")

    def test_not_exposed_has_reasons(self):
        for key, reason in NOT_EXPOSED.items():
            self.assertTrue(reason.strip(), key)
            self.assertNotIn(key, ui_exposed_keys())
