# SPDX-License-Identifier: AGPL-3.0-only
"""Reuse opened config decks until choice.toml or plugin files change."""

from __future__ import annotations

import inspect
from pathlib import Path

from choice.bounded_cache import LruDict
from choice.load import Opened
from choice.open import open_config, resolve
from choice.swipe_plugin import SwipePlugin

_CACHE: LruDict[str, tuple[int, int, Opened]] = LruDict(8)


def _mtime_ns(path: Path) -> int:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0


def _plugin_watch_mtime(opened: Opened) -> int:
    stamp = 0
    for deck in opened.decks:
        plugin = deck.plugin
        if not isinstance(plugin, SwipePlugin):
            continue
        stamp = max(stamp, _mtime_ns(plugin.folder / "deck.py"))
        try:
            mod_file = inspect.getfile(type(plugin.obj))
            stamp = max(stamp, _mtime_ns(Path(mod_file)))
        except (OSError, TypeError):
            continue
    return stamp


def open_library(path: Path) -> Opened:
    path = path.expanduser()
    resolved = path.resolve()
    if resolved.is_file() and resolved.suffix.lower() in {".toml", ".json"}:
        key = str(resolved)
        mtime = _mtime_ns(resolved)
        hit = _CACHE.get(key)
        if hit and hit[0] == mtime and hit[1] == _plugin_watch_mtime(hit[2]):
            return hit[2]
        opened = open_config(resolved)
        watch = _plugin_watch_mtime(opened)
        _CACHE.set(key, (mtime, watch, opened))
        return opened
    return resolve(resolved)


def bust_config(path: Path) -> None:
    path = path.expanduser().resolve()
    if path.is_file():
        _CACHE.pop(str(path))


def reload_library(path: Path) -> Opened:
    bust_config(path)
    return open_library(path)
