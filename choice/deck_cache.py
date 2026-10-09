# SPDX-License-Identifier: AGPL-3.0-only
"""Short-lived item list cache so large folders are not rescanned on every swipe."""

from __future__ import annotations

import time

from choice.bounded_cache import LruDict
from choice.deck_index import record_items
from choice.load import Deck

_TTL = 1.0
_cache: LruDict[str, tuple[float, tuple, list, list]] = LruDict(64)


def load_items(deck: Deck) -> tuple[list, list]:
    key = f"{deck.id}:{deck.state_dir}"
    stamp = _stamp(deck)
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and hit[0] >= now and hit[1] == stamp:
        return hit[2], hit[3]
    items, warnings = deck.load_items()
    record_items(deck, items)
    _cache.set(key, (now + _TTL, stamp, items, warnings))
    return items, warnings


def bust(deck: Deck) -> None:
    from choice.deck_index import clear_index
    from choice.folder_list_cache import invalidate_under

    key = f"{deck.id}:{deck.state_dir}"
    _cache.pop(key)
    if getattr(deck, "folder_scan", None) is not None:
        invalidate_under(deck.root)
    clear_index(deck)


def _stamp(deck: Deck) -> tuple:
    scan = getattr(deck, "folder_scan", None)
    if scan is not None:
        from choice.folder_list_cache import cached_list_files

        skip_dirs = set(scan.sort_dirs(deck.root))
        skip_dirs.add((deck.root / ".choice").resolve())
        files = cached_list_files(deck.root, scan.recursive, skip_dirs)
        from choice.folder_list_cache import _stamp as folder_stamp

        return ("folder", folder_stamp(files))
    root = deck.root
    try:
        return ("root", root.stat().st_mtime_ns)
    except OSError:
        return ("root", 0)
