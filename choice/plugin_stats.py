# SPDX-License-Identifier: AGPL-3.0-only
"""Plugin stats() helpers (endless decks, custom count labels)."""

from __future__ import annotations

import time

from choice.bounded_cache import LruDict
from choice.load import Deck

_TTL = 30.0
_cache: LruDict[str, tuple[float, dict]] = LruDict(128)


def _read_stats(plugin) -> dict:
    for target in (plugin, getattr(plugin, "obj", None)):
        if target is None:
            continue
        stats_fn = getattr(target, "stats", None)
        if not callable(stats_fn):
            continue
        try:
            raw = stats_fn()
        except Exception:
            continue
        if isinstance(raw, dict):
            return raw
    return {}


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


def _stats_label(raw: dict) -> str | None:
    label = raw.get("count_label")
    if isinstance(label, str) and label.strip():
        return label.strip()
    return None


def endless_display(deck: Deck, *, has_total: bool | None = None) -> tuple[bool, str | None]:
    """True when stats requests endless-style counts; second value is optional label."""
    raw = plugin_stats_raw(deck)
    label = _stats_label(raw)
    if raw.get("endless") is True:
        return True, label or "∞"
    if raw.get("endless") is False:
        return False, label
    if has_total is False:
        return True, label or "∞"
    return False, label


def apply_endless_counts(deck: Deck, payload: dict) -> dict:
    has_total = payload.get("total") is not None
    active, label = endless_display(deck, has_total=has_total)
    payload = dict(payload)
    if active:
        payload["endless"] = True
        if label:
            payload["count_label"] = label
        payload["meter"] = False
        payload["left"] = None
        payload["total"] = None
        return payload
    if label:
        payload["count_label"] = label
    return payload
