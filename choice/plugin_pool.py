# SPDX-License-Identifier: AGPL-3.0-only
"""Long-lived deck.py plugin instances (reload on deck.py mtime only)."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from collections.abc import Callable
from typing import Any

from choice.swipe_plugin import SwipePlugin

_lock = threading.Lock()
_cache: dict[str, SwipePlugin] = {}


def cache_key(folder: Path, deck_id: str, options: dict[str, Any]) -> str:
    deck_py = folder / "deck.py"
    try:
        mtime = deck_py.stat().st_mtime_ns
    except OSError:
        mtime = 0
    opts = json.dumps(options or {}, sort_keys=True, default=str)
    return f"{deck_id}|{folder.resolve()}|{mtime}|{opts}"


def get_plugin(
    folder: Path,
    deck_id: str,
    options: dict[str, Any],
    loader: Callable[[], Any],
) -> SwipePlugin:
    key = cache_key(folder, deck_id, options)
    with _lock:
        hit = _cache.get(key)
        if hit is not None:
            return hit
        for old_key, old in list(_cache.items()):
            if not old_key.startswith(f"{deck_id}|{folder.resolve()}|"):
                continue
            if old_key == key:
                continue
            _shutdown(old)
            _cache.pop(old_key, None)
        obj = loader()
        title = str(getattr(obj, "title", deck_id))
        plugin = SwipePlugin(obj=obj, folder=folder, deck_id=deck_id, title=title)
        _cache[key] = plugin
        return plugin


def _shutdown(plugin: SwipePlugin) -> None:
    for name in ("close", "shutdown", "stop"):
        fn = getattr(plugin.obj, name, None)
        if callable(fn):
            try:
                fn()
            except Exception:
                pass
            return


def clear_pool() -> None:
    with _lock:
        for plugin in _cache.values():
            _shutdown(plugin)
        _cache.clear()
