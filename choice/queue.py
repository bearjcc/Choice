# SPDX-License-Identifier: AGPL-3.0-only
"""Paged item queue with snapshot tokens (ported from Swipe)."""

from __future__ import annotations

import secrets
import threading
import time
from collections import OrderedDict

PAGE_SIZE = 200
SNAP_TTL = 600
_MAX_SNAPS = 6

_lock = threading.Lock()
_snaps: dict[str, OrderedDict[str, tuple[float, list]]] = {}


def page_items(
    deck_key: str, all_items: list, offset: int = 0, limit: int = PAGE_SIZE
) -> tuple[list, str]:
    """Return a slice and an opaque snapshot token for stable paging."""
    limit = max(1, min(limit, PAGE_SIZE))
    slice_items = all_items[offset : offset + limit]
    token = secrets.token_hex(8)
    with _lock:
        deck_snaps = _snaps.setdefault(deck_key, OrderedDict())
        deck_snaps[token] = (time.time(), list(slice_items))
        while len(deck_snaps) > _MAX_SNAPS:
            deck_snaps.popitem(last=False)
    return slice_items, token


def clear_deck_snapshots(deck_key: str) -> None:
    with _lock:
        _snaps.pop(deck_key, None)


def clear_all_snapshots() -> None:
    with _lock:
        _snaps.clear()


def resolve_token(deck_key: str, token: str) -> list | None:
    with _lock:
        deck_snaps = _snaps.get(deck_key)
        if not deck_snaps or token not in deck_snaps:
            return None
        ts, items = deck_snaps[token]
        if time.time() - ts > SNAP_TTL:
            del deck_snaps[token]
            return None
        return items
