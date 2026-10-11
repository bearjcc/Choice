# SPDX-License-Identifier: AGPL-3.0-only
"""Track in-process reads of deck media files (Windows rename safety)."""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from pathlib import Path

_lock = threading.Lock()
_inflight: dict[str, int] = {}


@contextmanager
def hold_source_read(path: Path):
    key = str(path.resolve())
    with _lock:
        _inflight[key] = _inflight.get(key, 0) + 1
    try:
        yield
    finally:
        with _lock:
            count = _inflight.get(key, 0) - 1
            if count <= 0:
                _inflight.pop(key, None)
            else:
                _inflight[key] = count


def source_readers(path: Path) -> int:
    key = str(path.resolve())
    with _lock:
        return _inflight.get(key, 0)


def wait_source_idle(path: Path, timeout: float = 5.0, poll: float = 0.02) -> bool:
    deadline = time.monotonic() + timeout
    key = str(path.resolve())
    while time.monotonic() < deadline:
        with _lock:
            if _inflight.get(key, 0) == 0:
                return True
        time.sleep(poll)
    with _lock:
        return _inflight.get(key, 0) == 0
