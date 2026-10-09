# SPDX-License-Identifier: AGPL-3.0-only
"""Atomic file replace with retries for Windows sharing violations."""

from __future__ import annotations

import os
import time
from pathlib import Path

_WIN_SHARING = {5, 13, 32}


def atomic_replace(tmp: Path, dest: Path, *, attempts: int = 12) -> None:
    delays = (0.001, 0.002, 0.005, 0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.5, 0.5, 1.0)
    last: OSError | None = None
    for i in range(attempts):
        try:
            os.replace(tmp, dest)
            return
        except OSError as exc:
            last = exc
            code = getattr(exc, "winerror", None)
            if code is None:
                code = exc.errno
            if code not in _WIN_SHARING:
                raise
            time.sleep(delays[min(i, len(delays) - 1)])
    if last is not None:
        raise last
