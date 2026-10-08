# SPDX-License-Identifier: AGPL-3.0-only
"""Cheap deck-list summaries without loading every plugin on each index request."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from choice.load import Deck, Item

_INDEX_TTL = 45.0
_list_locks: dict[str, threading.Lock] = {}
_guard = threading.Lock()
_index: dict[str, tuple[float, _Snapshot]] = {}


@dataclass
class _Snapshot:
    ids: frozenset[str]
    plugin_decided: frozenset[str]


def list_lock(deck: Deck) -> threading.Lock:
    key = str(deck.state_dir)
    with _guard:
        if key not in _list_locks:
            _list_locks[key] = threading.Lock()
        return _list_locks[key]


def record_items(deck: Deck, items: list[Item]) -> None:
    ids = frozenset(item.id for item in items)
    plugin_decided = frozenset(
        item.id for item in items if item.plugin_decided or item.fields.get("plugin_decided")
    )
    key = str(deck.state_dir)
    with _guard:
        snap = _Snapshot(ids=ids, plugin_decided=plugin_decided)
        _index[key] = (time.monotonic() + _INDEX_TTL, snap)


def snapshot(deck: Deck) -> _Snapshot | None:
    key = str(deck.state_dir)
    with _guard:
        hit = _index.get(key)
    if not hit:
        return None
    expires, snap = hit
    if expires < time.monotonic():
        with _guard:
            _index.pop(key, None)
        return None
    return snap


def clear_index(deck: Deck) -> None:
    with _guard:
        _index.pop(str(deck.state_dir), None)
