# SPDX-License-Identifier: AGPL-3.0-only
"""Plugin stats() helpers (endless decks, custom count labels)."""

from __future__ import annotations

import time

from choice.bounded_cache import LruDict
from choice.load import Deck

_TTL = 30.0
_cache: LruDict[str, tuple[float, dict]] = LruDict(128)


def _read_stats(plugin) -> dict:
    stats_fn = getattr(plugin, "stats", None)
    if not callable(stats_fn):
        return {}
    try:
        raw = stats_fn()
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    return raw


def plugin_stats_raw(deck: Deck) -> dict:
    plugin = deck.plugin
    if plugin is None or deck.problem:
        return {}
    key = str(deck.state_dir)
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and hit[0] >= now:
        return dict(hit[1])
    data = _read_stats(plugin)
    _cache.set(key, (now + _TTL, dict(data)))
    return data


def clear_plugin_stats_cache(deck: Deck) -> None:
    _cache.pop(str(deck.state_dir))


def endless_display(deck: Deck) -> tuple[bool, str | None]:
    """True when stats requests endless-style counts; second value is header label."""
    raw = plugin_stats_raw(deck)
    endless = bool(raw.get("endless"))
    label = raw.get("count_label")
    if isinstance(label, str) and label.strip():
        label = label.strip()
        return True, label
    if endless:
        return True, "∞"
    return False, None


def apply_endless_counts(deck: Deck, payload: dict) -> dict:
    active, label = endless_display(deck)
    if not active:
        return payload
    payload = dict(payload)
    payload["endless"] = True
    if label:
        payload["count_label"] = label
    payload["meter"] = False
    payload["left"] = None
    payload["total"] = None
    return payload
