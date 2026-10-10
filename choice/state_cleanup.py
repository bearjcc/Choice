# SPDX-License-Identifier: AGPL-3.0-only
"""Remove stale atomic-write temp files from state directories."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

_TMP_SUFFIX = re.compile(r"\.(\d+)\.tmp$")
_DEFAULT_MAX_AGE = 600.0


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def cleanup_atomic_tmp_in(
    directory: Path,
    *,
    max_age_seconds: float = _DEFAULT_MAX_AGE,
    now: float | None = None,
) -> list[Path]:
    """Delete ``*.<pid>.tmp`` files when the pid is gone or the file is old enough."""
    removed: list[Path] = []
    if not directory.is_dir():
        return removed
    clock = now if now is not None else time.time()
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        match = _TMP_SUFFIX.search(path.name)
        if not match:
            continue
        pid = int(match.group(1))
        try:
            age = clock - path.stat().st_mtime
        except OSError:
            continue
        if pid_alive(pid) and age < max_age_seconds:
            continue
        try:
            path.unlink()
            removed.append(path)
        except OSError:
            continue
    return removed


def cleanup_state_dirs(directories: list[Path], **kwargs) -> list[Path]:
    seen: set[Path] = set()
    removed: list[Path] = []
    for directory in directories:
        key = directory.resolve()
        if key in seen:
            continue
        seen.add(key)
        removed.extend(cleanup_atomic_tmp_in(directory, **kwargs))
    return removed
