# SPDX-License-Identifier: AGPL-3.0-only

import subprocess
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_FRAGMENTS = (
    ".egg-info/",
    ".pytest_cache/",
    ".ruff_cache/",
    "examples/taste/.choice/",
    "examples/yes-no/.choice/decisions.jsonl",
    "examples/taste/.choice/decisions.jsonl",
)

ZIP_EXCLUDES = [
    "*/.git/*",
    ".git/*",
    "uploads/*",
    "*/__pycache__/*",
    "*.pyc",
    ".ruff_cache/*",
    "*/.ruff_cache/*",
    ".pytest_cache/*",
    "*/.pytest_cache/*",
    "build/*",
    "*/build/*",
    "*.egg-info/*",
    "*/*.egg-info/*",
    ".choice-smoke-state/*",
    "examples/*/.choice/*",
    "examples/**/.choice/**",
]


def build_release_zip(dest: Path) -> None:
    args = ["zip", "-q", "-r", str(dest), "."]
    for pattern in ZIP_EXCLUDES:
        args.extend(["-x", pattern])
    subprocess.run(args, check=True, cwd=ROOT)


class ReleaseZipTests(unittest.TestCase):
    def test_release_zip_has_no_forbidden_paths(self):
        out = ROOT / "tmp-release-test.zip"
        if out.exists():
            out.unlink()
        build_release_zip(out)
        with zipfile.ZipFile(out) as archive:
            names = archive.namelist()
        for bad in FORBIDDEN_FRAGMENTS:
            hits = [name for name in names if bad in name.replace("\\", "/")]
            self.assertEqual(hits, [], msg=f"forbidden {bad!r}: {hits[:5]}")
        out.unlink(missing_ok=True)

    def test_shell_script_matches_python_exclusions(self):
        script = ROOT / "scripts" / "make_release_zip.sh"
        self.assertTrue(script.is_file())
        text = script.read_text(encoding="utf-8")
        self.assertIn("egg-info", text)
        self.assertIn("pytest_cache", text)
