# SPDX-License-Identifier: AGPL-3.0-only
"""Reuse opened config decks until choice.toml or plugin files change."""

from __future__ import annotations

from pathlib import Path

from choice.bounded_cache import LruDict
from choice.load import Opened
from choice.open import open_config, resolve
from choice.plugin_pool import clear_pool, deck_py_fingerprint
from choice.swipe_plugin import SwipePlugin, purge_swipe_modules

_CACHE: LruDict[str, tuple[int, str, Opened]] = LruDict(8)


def _mtime_ns(path: Path) -> int:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0


def _plugin_watch_stamp(opened: Opened) -> str:
    parts: list[str] = []
    for deck in opened.decks:
        plugin = deck.plugin
        if not isinstance(plugin, SwipePlugin):
            continue
        parts.append(deck_py_fingerprint(plugin.folder / "deck.py"))
    return "|".join(sorted(parts))


def _purge_plugin_caches(opened: Opened | None) -> None:
    from choice.deck_cache import bust
    from choice.deck_index import clear_index, clear_warm_scheduled
    from choice.queue import clear_deck_snapshots

    if opened is not None:
        for deck in opened.decks:
            bust(deck)
            clear_index(deck)
            clear_warm_scheduled(deck)
            clear_deck_snapshots(deck.id)
    clear_pool()
    purge_swipe_modules()


def open_library(path: Path) -> Opened:
    path = path.expanduser()
    resolved = path.resolve()
    if resolved.is_file() and resolved.suffix.lower() in {".toml", ".json"}:
        key = str(resolved)
        mtime = _mtime_ns(resolved)
        hit = _CACHE.get(key)
        if hit is not None:
            opened = hit[2]
            live = _plugin_watch_stamp(opened)
            if hit[0] == mtime and hit[1] == live:
                return opened
            return reload_library(resolved)
        opened = open_config(resolved)
        stamp = _plugin_watch_stamp(opened)
        _CACHE.set(key, (mtime, stamp, opened))
        return opened
    return resolve(resolved)


def bust_config(path: Path) -> None:
    path = path.expanduser().resolve()
    if path.is_file():
        _CACHE.pop(str(path))


def reload_library(path: Path) -> Opened:
    path = path.expanduser().resolve()
    if path.is_file() and path.suffix.lower() in {".toml", ".json"}:
        key = str(path)
        prev = _CACHE.get(key)
        _purge_plugin_caches(prev[2] if prev else None)
        bust_config(path)
        opened = open_config(path)
        stamp = _plugin_watch_stamp(opened)
        _CACHE.set(key, (_mtime_ns(path), stamp, opened))
        return opened
    bust_config(path)
    return resolve(path)
