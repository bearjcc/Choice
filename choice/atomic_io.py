# SPDX-License-Identifier: AGPL-3.0-only
"""Atomic file replace with retries for Windows sharing violations."""

from __future__ import annotations

import errno
import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

_WIN_SHARING = {5, 13, 32}
_MISSING_PATH = {2, 3}  # ENOENT / Windows ERROR_PATH_NOT_FOUND
_path_locks: dict[str, threading.Lock] = {}
_lock_guard = threading.Lock()


def _path_lock(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _lock_guard:
        lock = _path_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _path_locks[key] = lock
        return lock


def write_text_atomic(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = _path_lock(path)
    with lock:
        prefix = f"{path.name}.{os.getpid()}.{threading.get_ident()}."
        fd, tmp_name = tempfile.mkstemp(prefix=prefix, suffix=".tmp", dir=path.parent)
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding=encoding) as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            atomic_replace(tmp, path)
        finally:
            if tmp.is_file():
                try:
                    tmp.unlink()
                except OSError:
                    pass


def write_json_atomic(
    path: Path,
    payload: Any,
    *,
    indent: int | None = None,
    trailing_newline: bool = False,
) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=indent)
    if trailing_newline:
        text += "\n"
    write_text_atomic(path, text)


def _unlink_tmp(tmp: Path) -> None:
    if tmp.is_file():
        try:
            tmp.unlink()
        except OSError:
            pass


def atomic_replace(tmp: Path, dest: Path, *, attempts: int = 12) -> None:
    delays = (0.001, 0.002, 0.005, 0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.5, 0.5, 1.0)
    last: OSError | None = None
    for i in range(attempts):
        try:
            if not dest.parent.is_dir():
                _unlink_tmp(tmp)
                raise OSError(
                    errno.ENOENT,
                    "Destination directory is missing",
                    str(dest.parent),
                )
            os.replace(tmp, dest)
            return
        except OSError as exc:
            last = exc
            code = getattr(exc, "winerror", None)
            if code is None:
                code = exc.errno
            if code in _MISSING_PATH:
                _unlink_tmp(tmp)
                raise
            if code not in _WIN_SHARING:
                raise
            time.sleep(delays[min(i, len(delays) - 1)])
    if last is not None:
        raise last
