# SPDX-License-Identifier: AGPL-3.0-only
"""Short-lived item list cache so large folders are not rescanned on every swipe."""

from __future__ import annotations

import json
import logging
import time

from choice.bounded_cache import LruDict
from choice.deck_index import record_items, snapshot
from choice.load import Deck, DeckProblem

_log = logging.getLogger(__name__)

_TTL = 1.0
_cache: LruDict[str, tuple[float, tuple, list, list]] = LruDict(64)


def load_items(deck: Deck) -> tuple[list, list]:
    from choice.plugin_filters import get_request_filter, selection_to_plugin_filter

    filt = selection_to_plugin_filter(get_request_filter())
    filt_key = json.dumps(filt, sort_keys=True) if filt else ""
    key = f"{deck.id}:{deck.state_dir}:{filt_key}"
    stamp = _stamp(deck, filt_key)
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
    from choice.served_items import record_served_items

    record_served_items(deck, items)
    _cache.set(key, (now + _TTL, stamp, items, warnings))
    return items, warnings


def bust(deck: Deck, *, invalidate_folder: bool = False) -> None:
    from choice.deck_index import clear_index
    from choice.folder_list_cache import invalidate_under

    prefix = f"{deck.id}:{deck.state_dir}"
    for key, _ in _cache.items():
        if key == prefix or key.startswith(prefix + ":"):
            _cache.pop(key)
    if invalidate_folder and getattr(deck, "folder_scan", None) is not None:
        invalidate_under(deck.root)
    clear_index(deck)


def _stamp(deck: Deck, filt_key: str = "") -> tuple:
    scan = getattr(deck, "folder_scan", None)
    if scan is not None:
        from choice.folder_index import generation

        return ("folder_index", generation(deck.state_dir), filt_key)
    if deck.plugin is not None:
        from choice.deck_index import list_generation, snapshot_cache_key

        return ("plugin", snapshot_cache_key(deck), list_generation(deck), filt_key)
    root = deck.root
    try:
        return ("root", root.stat().st_mtime_ns, filt_key)
    except OSError:
        return ("root", 0, filt_key)
