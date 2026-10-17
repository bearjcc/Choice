# SPDX-License-Identifier: AGPL-3.0-only
"""Deck-declared plugin filters (list_items / stats filter= kwarg)."""

from __future__ import annotations

import base64
import contextvars
import json
from typing import Any

from choice.swipe_plugin import SwipePlugin, _accepts

_filter_ctx: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "choice_plugin_filter", default=None
)


def set_request_filter(payload: dict | None) -> contextvars.Token:
    return _filter_ctx.set(payload)


def reset_request_filter(token: contextvars.Token) -> None:
    _filter_ctx.reset(token)


def get_request_filter() -> dict | None:
    return _filter_ctx.get()


def plugin_declares_filters(plugin: Any) -> bool:
    obj = plugin.obj if isinstance(plugin, SwipePlugin) else plugin
    return callable(getattr(obj, "filters", None))


def fetch_filter_schema(plugin: Any) -> dict | None:
    obj = plugin.obj if isinstance(plugin, SwipePlugin) else plugin
    fn = getattr(obj, "filters", None)
    if not callable(fn):
        return None
    try:
        raw = fn()
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    filters = raw.get("filters")
    if not isinstance(filters, list):
        return None
    return raw


def plugin_accepts_list_filter(plugin: Any) -> bool:
    if isinstance(plugin, SwipePlugin):
        return _accepts(plugin.obj.list_items, "filter")
    fn = getattr(plugin, "list_items", None)
    return callable(fn) and _accepts(fn, "filter")


def plugin_accepts_stats_filter(plugin: Any) -> bool:
    if isinstance(plugin, SwipePlugin):
        return _accepts(getattr(plugin.obj, "stats", None) or (lambda: None), "filter")
    fn = getattr(plugin, "stats", None)
    return callable(fn) and _accepts(fn, "filter")


def should_pass_filter(plugin: Any, selection: dict | None) -> bool:
    if not selection:
        return False
    if plugin_declares_filters(plugin):
        return True
    return plugin_accepts_list_filter(plugin)


def selection_to_plugin_filter(selection: dict | None) -> dict | None:
    """Build list_items(filter=...) payload from UI selection."""
    if not selection or not isinstance(selection, dict):
        return None
    out: dict[str, Any] = {}
    for key, raw in selection.items():
        if key == "_sort":
            if raw:
                out["_sort"] = str(raw)
            continue
        if not isinstance(raw, dict):
            continue
        values = raw.get("values")
        if not isinstance(values, list) or not values:
            continue
        clean = [str(v) for v in values if v is not None and str(v)]
        if not clean:
            continue
        entry: dict[str, Any] = {"values": clean}
        match = raw.get("match")
        if match in {"all", "any"}:
            entry["match"] = match
        out[str(key)] = entry
    if not out:
        return None
    return out


def decode_filter_param(raw: str | None) -> dict | None:
    if not raw or not str(raw).strip():
        return None
    text = str(raw).strip()
    pad = "=" * (-len(text) % 4)
    try:
        data = base64.urlsafe_b64decode(text + pad)
        parsed = json.loads(data.decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def plugin_filter_cache_key(deck) -> str:
    """Deck list cache key including active plugin filter (matches deck_cache / deck_index)."""
    from choice.deck_index import snapshot_cache_key

    return snapshot_cache_key(deck)


def encode_filter_param(selection: dict | None) -> str:
    if not selection:
        return ""
    raw = json.dumps(selection, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
