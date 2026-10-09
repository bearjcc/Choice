# SPDX-License-Identifier: AGPL-3.0-only
"""Reuse opened config decks until choice.toml changes."""

from __future__ import annotations

from pathlib import Path

from choice.bounded_cache import LruDict
from choice.load import Opened
from choice.open import open_config, resolve

_CACHE: LruDict[str, tuple[int, Opened]] = LruDict(8)


def _mtime_ns(path: Path) -> int:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0


def open_library(path: Path) -> Opened:
    path = path.expanduser()
    resolved = path.resolve()
    if resolved.is_file() and resolved.suffix.lower() in {".toml", ".json"}:
        key = str(resolved)
        mtime = _mtime_ns(resolved)
        hit = _CACHE.get(key)
        if hit and hit[0] == mtime:
            return hit[1]
        opened = open_config(resolved)
        _CACHE.set(key, (mtime, opened))
        return opened
    return resolve(resolved)


def bust_config(path: Path) -> None:
    path = path.expanduser().resolve()
    if path.is_file():
        _CACHE.pop(str(path))
