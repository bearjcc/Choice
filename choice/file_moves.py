# SPDX-License-Identifier: AGPL-3.0-only
"""Deck file moves without silent copy-and-leave-source failures."""

from __future__ import annotations

import filecmp
import json
import os
import shutil
import time
import uuid
from pathlib import Path

from choice.atomic_io import atomic_replace

_WIN_SHARING = {5, 13, 32}
_REPLACE_DELAYS = (0.001, 0.002, 0.005, 0.01, 0.02, 0.04, 0.08, 0.16)


class MoveNotReady(Exception):
    """Transient move failure; caller should retry later."""


def same_volume(src: Path, dest: Path) -> bool:
    try:
        return os.stat(src).st_dev == os.stat(dest.parent).st_dev
    except OSError:
        return True


def files_equal(a: Path, b: Path) -> bool:
    if not a.is_file() or not b.is_file():
        return False
    try:
        return filecmp.cmp(a, b, shallow=False)
    except OSError:
        return False


def fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def move_file(src: Path, dest: Path) -> None:
    """Move src to dest. Source must be gone before this returns."""
    from choice.source_reads import wait_source_idle

    wait_source_idle(src, timeout=8.0)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not src.is_file():
        if dest.is_file():
            return
        raise MoveNotReady("source missing")
    if dest.is_file():
        if files_equal(src, dest):
            remove_source(src)
            return
        raise MoveNotReady("destination exists with different content")
    if same_volume(src, dest):
        replace_same_volume(src, dest)
    else:
        cross_volume_move(src, dest)
    if src.is_file():
        raise MoveNotReady("source still present after move")


def copy_file(src: Path, dest: Path) -> None:
    if dest.is_file():
        return
    if not src.is_file():
        raise MoveNotReady("source missing")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if same_volume(src, dest):
        shutil.copy2(src, dest)
        return
    tmp = _temp_dest(dest)
    try:
        shutil.copy2(src, tmp)
        fsync_file(tmp)
        atomic_replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)
    if not dest.is_file():
        raise MoveNotReady("copy incomplete")


def remove_source(src: Path) -> None:
    if not src.is_file():
        return
    last: OSError | None = None
    for i, delay in enumerate((*_REPLACE_DELAYS, 0.05, 0.1)):
        try:
            src.unlink()
            return
        except OSError as exc:
            last = exc
            if not _sharing_violation(exc):
                raise
            time.sleep(delay)
    raise MoveNotReady(str(last) if last else "cannot delete source")


def replace_same_volume(src: Path, dest: Path) -> None:
    last: OSError | None = None
    for i, delay in enumerate((*_REPLACE_DELAYS, 0.05, 0.1, 0.2)):
        try:
            os.replace(src, dest)
            return
        except OSError as exc:
            last = exc
            if not _sharing_violation(exc):
                raise
            time.sleep(delay)
    raise MoveNotReady(str(last) if last else "rename blocked")


def cross_volume_move(src: Path, dest: Path) -> None:
    tmp = _temp_dest(dest)
    try:
        shutil.copy2(src, tmp)
        fsync_file(tmp)
        atomic_replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)
    remove_source(src)


def conflict_dest_path(dest: Path) -> Path:
    stem, suffix = dest.stem, dest.suffix
    parent = dest.parent
    for n in range(1, 10_000):
        candidate = parent / f"{stem}.choice-conflict-{n}{suffix}"
        if not candidate.exists():
            return candidate
    raise OSError(f"no free conflict name near {dest}")


def log_move_conflict(state_dir: Path, record: dict) -> None:
    path = state_dir / "move_conflicts.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _temp_dest(dest: Path) -> Path:
    return dest.with_name(f".{dest.name}.choice-{uuid.uuid4().hex}.tmp")


def _sharing_violation(exc: OSError) -> bool:
    code = getattr(exc, "winerror", None)
    if code is None:
        code = exc.errno
    return code in _WIN_SHARING
