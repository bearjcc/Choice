# SPDX-License-Identifier: AGPL-3.0-only

import subprocess
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _git_checkout() -> bool:
    proc = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0

FORBIDDEN_FRAGMENTS = (
    ".egg-info/",
    ".pytest_cache/",
    ".ruff_cache/",
    "node_modules/",
    "PrintDeps.exe",
    "examples/taste/.choice/",
    "examples/yes-no/.choice/decisions.jsonl",
    "examples/taste/.choice/decisions.jsonl",
    "tests/fixtures/modal_layout/state/",
    "tests/fixtures/modal_layout/.choice/",
)


def git_tracked_files(ref: str = "HEAD") -> set[str]:
    proc = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", ref],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return {line.strip() for line in proc.stdout.splitlines() if line.strip()}


def build_release_zip(dest: Path, ref: str = "HEAD") -> None:
    env = {"CHOICE_RELEASE_GIT_REF": ref}
    subprocess.run(
        ["bash", str(ROOT / "scripts" / "make_release_zip.sh"), str(dest)],
        check=True,
        cwd=ROOT,
        env={**dict(__import__("os").environ), **env},
    )


class ReleaseZipTests(unittest.TestCase):
    @unittest.skipUnless(_git_checkout(), "not run inside a git checkout")
    def test_release_zip_matches_git_tree_only(self):
        out = ROOT / "tmp-release-test.zip"
        if out.exists():
            out.unlink()
        ref = "HEAD"
        build_release_zip(out, ref=ref)
        tracked = git_tracked_files(ref)
        with zipfile.ZipFile(out) as archive:
            names = {name for name in archive.namelist() if not name.endswith("/")}
        self.assertEqual(names, tracked)
        for bad in FORBIDDEN_FRAGMENTS:
            hits = [name for name in names if bad in name.replace("\\", "/")]
            self.assertEqual(hits, [], msg=f"forbidden {bad!r}: {hits[:5]}")
        out.unlink(missing_ok=True)

    def test_shell_script_uses_git_archive(self):
        script = ROOT / "scripts" / "make_release_zip.sh"
        self.assertTrue(script.is_file())
        text = script.read_text(encoding="utf-8")
        self.assertIn("git archive", text)
        self.assertNotIn("zip -q -r", text)
