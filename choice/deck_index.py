# SPDX-License-Identifier: AGPL-3.0-only
"""Cheap deck-list summaries without loading every plugin on each index request."""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass

from choice.bounded_cache import LruDict
from choice.load import Deck, Item

_INDEX_TTL = 45.0
_COUNTS_NAME = "list_counts.json"
_list_locks: LruDict[str, threading.RLock] = LruDict(128)
_guard = threading.Lock()
_index: LruDict[str, tuple[float, _Snapshot]] = LruDict(128)
_warm_scheduled: set[str] = set()


@dataclass
class _Snapshot:
    ids: frozenset[str]
    plugin_decided: frozenset[str]
    order: list[str]
    items: list[Item] | None = None


def list_lock(deck: Deck) -> threading.RLock:
    key = str(deck.state_dir)
    with _guard:
        lock = _list_locks.get(key)
        if lock is None:
            lock = threading.RLock()
            _list_locks.set(key, lock)
        return lock


def record_items(deck: Deck, items: list[Item]) -> None:
    order = [item.id for item in items]
    ids = frozenset(order)
    plugin_decided = frozenset(
        item.id for item in items if item.plugin_decided or item.fields.get("plugin_decided")
    )
    key = str(deck.state_dir)
    snap = _Snapshot(ids=ids, plugin_decided=plugin_decided, order=order, items=items)
    with _guard:
        _index.set(key, (time.monotonic() + _INDEX_TTL, snap))
    _persist_counts(deck, snap)


def snapshot(deck: Deck) -> _Snapshot | None:
    key = str(deck.state_dir)
    with _guard:
        hit = _index.get(key)
    if not hit:
        return None
    expires, snap = hit
    if expires < time.monotonic():
        with _guard:
            _index.pop(key)
        return None
    return snap


def clear_index(deck: Deck) -> None:
    with _guard:
        _index.pop(str(deck.state_dir))


def clear_warm_scheduled(deck: Deck) -> None:
    with _guard:
        _warm_scheduled.discard(str(deck.state_dir))


def ensure_plugin_snapshot(deck: Deck) -> None:
    """Load plugin items when the in-memory snapshot is missing."""
    if deck.plugin is None or deck.problem:
        return
    if snapshot(deck) is not None:
        return
    with list_lock(deck):
        if snapshot(deck) is not None:
            return
        try:
            deck.load_items()
        except Exception:
            return


def schedule_plugin_warm(deck: Deck) -> None:
    if os.environ.get("CHOICE_DISABLE_WARM"):
        return
    if deck.plugin is None or deck.problem:
        return
    key = str(deck.state_dir)
    with _guard:
        if key in _warm_scheduled:
            return
        _warm_scheduled.add(key)
    threading.Thread(target=_warm_worker, args=(deck,), name=f"warm-{deck.id}", daemon=True).start()


def _warm_worker(deck: Deck) -> None:
    with list_lock(deck):
        if snapshot(deck) is not None:
            return
        try:
            deck.load_items()
        except Exception:
            return


def _persist_counts(deck: Deck, snap: _Snapshot) -> None:
    from choice.atomic_io import write_json_atomic

    path = deck.state_dir / _COUNTS_NAME
    try:
        payload = {
            "total": len(snap.ids),
            "plugin_decided": sorted(snap.plugin_decided),
            "ids": sorted(snap.ids),
            "order": snap.order,
        }
        write_json_atomic(path, payload)
    except OSError:
        return


@dataclass
class PersistedSummary:
    total: int
    plugin_decided: frozenset[str]
    ids: frozenset[str]


def plugin_pile_counts(
    log_decided: set[str],
    universe: frozenset[str],
    plugin_decided: frozenset[str],
) -> tuple[int, int, int, int]:
    """Return total, decided, left, list_size for plugin home rows."""
    in_list = plugin_decided & universe
    pile_done = (log_decided | in_list) & universe
    left = len(universe) - len(pile_done)
    decided = len(log_decided | in_list)
    total = decided + left
    return total, decided, left, len(universe)


def refresh_persisted_summary(deck: Deck) -> PersistedSummary | None:
    """Reload the plugin list when persisted counts lack ids (pre-0.2.9 file)."""
    saved = persisted_summary(deck)
    if saved is None or saved.ids:
        return saved
    with list_lock(deck):
        saved = persisted_summary(deck)
        if saved is not None and saved.ids:
            return saved
        try:
            deck.load_items()
        except Exception:
            return saved
    return persisted_summary(deck)


def persisted_summary(deck: Deck) -> PersistedSummary | None:
    path = deck.state_dir / _COUNTS_NAME
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    total = data.get("total")
    if not isinstance(total, int) or total < 0:
        return None
    decided_raw = data.get("plugin_decided") or []
    plugin_decided = frozenset(str(x) for x in decided_raw if x)
    ids_raw = data.get("ids")
    if isinstance(ids_raw, list) and ids_raw:
        ids = frozenset(str(x) for x in ids_raw if x)
    else:
        ids = frozenset()
    return PersistedSummary(total=total, plugin_decided=plugin_decided, ids=ids)
