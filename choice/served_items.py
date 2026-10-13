# SPDX-License-Identifier: AGPL-3.0-only
"""Last item list returned to a client for a deck (media/decide lookup without reload)."""

from __future__ import annotations

from choice.bounded_cache import LruDict
from choice.load import Deck, Item

_served: LruDict[str, list[Item]] = LruDict(128)


def _key(deck: Deck) -> str:
    actor = getattr(deck, "actor", None) or ""
    return f"{deck.id}:{deck.state_dir}:{actor}"


def record_served_items(deck: Deck, items: list[Item]) -> None:
    if not items:
        return
    _served.set(_key(deck), list(items))


def last_served_items(deck: Deck) -> list[Item] | None:
    hit = _served.get(_key(deck))
    if hit:
        return list(hit)
    return None
