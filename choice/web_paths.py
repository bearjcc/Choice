# SPDX-License-Identifier: AGPL-3.0-only
"""Locate bundled web assets (works when frozen with PyInstaller/Nuitka)."""

from __future__ import annotations

import sys
from pathlib import Path


def web_root() -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidate = Path(meipass) / "choice" / "web"
        if candidate.is_dir():
            return candidate
    return Path(__file__).resolve().parent / "web"
