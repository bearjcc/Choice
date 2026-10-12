# SPDX-License-Identifier: AGPL-3.0-only

import os
from pathlib import Path

import pytest

os.environ.setdefault("CHOICE_SYNC_WORK", "1")


@pytest.fixture(autouse=True)
def _folder_scan_image_probe_for_tests(request, monkeypatch):
    """Many tests use one-byte .jpg stubs; production skips unreadable images."""
    if request.node.fspath and request.node.fspath.basename == "test_image_probe.py":
        return
    from choice import image_probe

    def _lenient(path: Path) -> bool:
        try:
            return path.stat().st_size > 0
        except OSError:
            return False

    monkeypatch.setattr(image_probe, "image_readable", _lenient)
