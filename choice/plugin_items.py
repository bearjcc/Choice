# SPDX-License-Identifier: AGPL-3.0-only
"""Resilient plugin list_items loading with partial progress and snapshot fallback."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from choice.deck_index import record_items, snapshot
from choice.load import Deck, Item

log = logging.getLogger(__name__)


def materialize_plugin_list(plugin: Any, deck: Deck) -> list[dict] | None:
    """Call list_items once; return a snapshot list or None on total failure."""
    try:
        raw = plugin.list_items()
    except Exception as exc:
        log.warning("plugin list_items failed for deck %s: %s", deck.id, exc, exc_info=True)
        return None
    if raw is None:
        return []
    try:
        return list(raw)
    except TypeError:
        log.warning("plugin list_items for deck %s did not return an iterable", deck.id)
        return None


def convert_plugin_rows(
    deck: Deck,
    rows: list[dict],
    folder,
    plugin: Any,
    converter: Callable[[dict, Any, Any], tuple[Item, list[str]]],
) -> tuple[list[Item], list[str]]:
    items: list[Item] = []
    warnings: list[str] = []
    for index, row in enumerate(rows):
        try:
            if not isinstance(row, dict):
                warnings.append(f"skipped non-object item at index {index}")
                continue
            item_id = str(row.get("id") or "")
            if not item_id:
                warnings.append("skipped item with no id")
                continue
            item, row_notes = converter(row, folder, plugin)
            warnings.extend(row_notes)
            items.append(item)
        except Exception as exc:
            log.warning(
                "plugin row %s failed for deck %s: %s",
                index,
                deck.id,
                exc,
                exc_info=True,
            )
            warnings.append(f"skipped item at index {index}: {exc}")
            continue
    return items, warnings


def fallback_items(deck: Deck, note: str) -> tuple[list[Item], list[str]] | None:
    snap = snapshot(deck)
    if snap is not None and snap.items:
        return list(snap.items), [note]
    if snap is not None and snap.order:
        return [], [note, "cached ids only; item bodies unavailable"]
    return None


def load_swipe_plugin_items(
    deck: Deck,
    plugin: Any,
    folder,
    converter: Callable[[dict, Any, Any], tuple[Item, list[str]]],
) -> tuple[list[Item], list[str]]:
    rows = materialize_plugin_list(plugin, deck)
    if rows is None:
        fb = fallback_items(deck, "using last good item list after plugin list_items error")
        if fb is not None:
            return fb
        return [], ["plugin list_items failed and no cached list is available"]

    items, warnings = convert_plugin_rows(deck, rows, folder, plugin, converter)
    if items:
        record_items(deck, items)
        return items, warnings

    fb = fallback_items(deck, "using last good item list after empty or failed conversion")
    if fb is not None:
        return fb[0], warnings + [fb[1][0]]
    return items, warnings
