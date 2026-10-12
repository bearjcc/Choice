# SPDX-License-Identifier: AGPL-3.0-only
"""Remove stale atomic-write temp files from state directories."""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

_LEGACY_TMP_SUFFIX = re.compile(r"\.(\d+)\.tmp$")
_DEFAULT_MAX_AGE = 600.0
_PROBE_MIN_AGE = 30.0


def _pid_alive_windows(pid: int) -> bool:
    import ctypes
    from ctypes import wintypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return True
        return int(code.value) == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        return _pid_alive_windows(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _is_atomic_tmp(path: Path) -> bool:
    name = path.name
    if not name.endswith(".tmp"):
        return False
    if _LEGACY_TMP_SUFFIX.search(name):
        return True
    # mkstemp temps: e.g. folder_index.json.<pid>.<tid>.<random>.tmp
    return ".json." in name or name.count(".") >= 3


def cleanup_atomic_tmp_in(
    directory: Path,
    *,
    max_age_seconds: float = _DEFAULT_MAX_AGE,
    now: float | None = None,
) -> list[Path]:
    """Delete atomic-write ``*.tmp`` files when they are old or the legacy pid is gone."""
    removed: list[Path] = []
    if not directory.is_dir():
        return removed
    clock = now if now is not None else time.time()
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        if not _is_atomic_tmp(path):
            continue
        try:
            age = clock - path.stat().st_mtime
        except OSError:
            continue
        legacy = _LEGACY_TMP_SUFFIX.search(path.name)
        if legacy is None:
            if age < max_age_seconds:
                continue
        else:
            pid = int(legacy.group(1))
            if age < max_age_seconds:
                if age < _PROBE_MIN_AGE:
                    continue
                if pid_alive(pid):
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
