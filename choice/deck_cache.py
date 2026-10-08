# SPDX-License-Identifier: AGPL-3.0-only
"""Short-lived item list cache so large folders are not rescanned on every swipe."""

from __future__ import annotations

import threading
import time

from choice.deck_index import record_items
from choice.load import Deck

_TTL = 1.0
_lock = threading.Lock()
_cache: dict[str, tuple[float, list, list]] = {}


def load_items(deck: Deck) -> tuple[list, list]:
    key = f"{deck.id}:{deck.state_dir}"
    stamp = _stamp(deck)
    now = time.monotonic()
    with _lock:
        hit = _cache.get(key)
        if hit and hit[0] >= now and hit[1] == stamp:
            return hit[2], hit[3]
    items, warnings = deck.load_items()
    record_items(deck, items)
    with _lock:
        _cache[key] = (now + _TTL, stamp, items, warnings)
    return items, warnings


def bust(deck: Deck) -> None:
    from choice.deck_index import clear_index

    key = f"{deck.id}:{deck.state_dir}"
    with _lock:
        _cache.pop(key, None)
    clear_index(deck)


def _stamp(deck: Deck) -> int:
    root = deck.root
    try:
        return root.stat().st_mtime_ns
    except OSError:
        return 0
