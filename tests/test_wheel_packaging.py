# SPDX-License-Identifier: AGPL-3.0-only

import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_WEB = {
    "choice/web/app.js",
    "choice/web/app.css",
    "choice/web/index.html",
    "choice/web/sw.js",
    "choice/web/action_icons.js",
    "choice/web/dialog_ui.js",
    "choice/web/pile_nav.js",
    "choice/web/swipe_ui.js",
}

FORBIDDEN_PREFIXES = (
    "tests/",
    "docs/",
    "examples/",
    "scripts/",
)


class WheelPackagingTests(unittest.TestCase):
    def test_wheel_contains_web_only_choice_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp) / "dist"
            subprocess.run(
                ["python3", "-m", "pip", "install", "build", "-q"],
                check=True,
                cwd=ROOT,
            )
            subprocess.run(
                ["python3", "-m", "build", "--wheel", "-o", str(dist)],
                check=True,
                cwd=ROOT,
            )
            wheels = list(dist.glob("*.whl"))
            self.assertEqual(len(wheels), 1)
            wheel = wheels[0]
            self.assertIn("choice_swipe", wheel.name)
            with zipfile.ZipFile(wheel) as archive:
                names = {n for n in archive.namelist() if not n.endswith("/")}
            self.assertTrue(any(n.startswith("choice/sources/") for n in names))
            for path in REQUIRED_WEB:
                hits = [n for n in names if n.endswith(path) or n == path]
                self.assertTrue(hits, f"missing {path} in wheel")
            for prefix in FORBIDDEN_PREFIXES:
                bad = [n for n in names if n.startswith(prefix)]
                self.assertEqual(bad, [], f"forbidden prefix {prefix}: {bad[:3]}")


if __name__ == "__main__":
    unittest.main()
