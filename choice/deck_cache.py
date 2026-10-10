# SPDX-License-Identifier: AGPL-3.0-only
"""Short-lived item list cache so large folders are not rescanned on every swipe."""

from __future__ import annotations

import time

import logging

from choice.bounded_cache import LruDict
from choice.deck_index import record_items, snapshot
from choice.load import Deck, DeckProblem

_log = logging.getLogger(__name__)

_TTL = 1.0
_cache: LruDict[str, tuple[float, tuple, list, list]] = LruDict(64)


def load_items(deck: Deck) -> tuple[list, list]:
    key = f"{deck.id}:{deck.state_dir}"
    stamp = _stamp(deck)
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and hit[0] >= now and hit[1] == stamp:
        return hit[2], hit[3]
    try:
        items, warnings = deck.load_items()
    except DeckProblem as exc:
        snap = snapshot(deck)
        if snap is not None and snap.items:
            _log.warning("deck load_items failed for %s: %s; using snapshot", deck.id, exc)
            items, warnings = list(snap.items), [str(exc)]
        else:
            raise
    else:
        if deck.plugin is None:
            record_items(deck, items)
    _cache.set(key, (now + _TTL, stamp, items, warnings))
    return items, warnings


def bust(deck: Deck, *, invalidate_folder: bool = False) -> None:
    from choice.deck_index import clear_index
    from choice.folder_list_cache import invalidate_under

    key = f"{deck.id}:{deck.state_dir}"
    _cache.pop(key)
    if invalidate_folder and getattr(deck, "folder_scan", None) is not None:
        invalidate_under(deck.root)
    clear_index(deck)


def _stamp(deck: Deck) -> tuple:
    scan = getattr(deck, "folder_scan", None)
    if scan is not None:
        from choice.folder_index import generation

        return ("folder_index", generation(deck.state_dir))
    root = deck.root
    try:
        return ("root", root.stat().st_mtime_ns)
    except OSError:
        return ("root", 0)
