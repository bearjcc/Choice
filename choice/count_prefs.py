# SPDX-License-Identifier: AGPL-3.0-only
"""Per-deck pile count display (saved in state dir)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from choice.load import Deck

_PREFS_FILE = "counts_prefs.json"
_MODES = frozenset({"auto", "on", "off"})
_LARGE_PILE = 5000
_STATS_FILE = "folder_stats.json"


def defaults_for(deck: Deck) -> str:
    raw = getattr(deck, "counts_defaults", None)
    if isinstance(raw, str) and raw in _MODES:
        return raw
    if isinstance(raw, dict):
        mode = raw.get("mode") or raw.get("counts")
        if isinstance(mode, str) and mode in _MODES:
            return mode
    view = getattr(deck, "view_defaults", None) or {}
    if isinstance(view, dict):
        nested = view.get("counts")
        if isinstance(nested, str) and nested in _MODES:
            return nested
        if isinstance(nested, dict):
            mode = nested.get("mode")
            if isinstance(mode, str) and mode in _MODES:
                return mode
    return "auto"


def prefs_path(state_dir: Path) -> Path:
    return state_dir / _PREFS_FILE


def load_counts_mode(deck: Deck) -> str:
    defaults = defaults_for(deck)
    path = prefs_path(deck.state_dir)
    if not path.is_file():
        return defaults
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return defaults
    if not isinstance(data, dict):
        return defaults
    mode = data.get("mode")
    if isinstance(mode, str) and mode in _MODES:
        return mode
    return defaults


def save_counts_mode(deck: Deck, mode: str) -> None:
    if mode not in _MODES:
        mode = "auto"
    path = prefs_path(deck.state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    from choice.atomic_io import write_json_atomic

    write_json_atomic(path, {"mode": mode}, indent=2, trailing_newline=True)


def counts_hidden(deck: Deck) -> bool:
    mode = load_counts_mode(deck)
    if mode == "on":
        return False
    if mode == "off":
        return True
    return auto_hide_counts(deck)


def auto_hide_counts(deck: Deck) -> bool:
    if deck.story:
        return True
    if deck.contest_kind == "rated":
        return True
    if getattr(deck, "source_type", None) == "rss":
        return True
    if deck.plugin is not None and deck.folder_scan is None:
        from choice.deck_index import persisted_summary, snapshot
        from choice.plugin_stats import endless_display

        if endless_display(deck)[0]:
            return True
        if snapshot(deck) is not None:
            return False
        saved = persisted_summary(deck)
        if saved is not None:
            size = len(saved.ids) if saved.ids else saved.total
            if size >= _LARGE_PILE:
                return True
            if saved.ids or saved.total > 0:
                return False
        return True
    pile_size = folder_pile_size(deck.state_dir)
    if pile_size is not None and pile_size >= _LARGE_PILE:
        return True
    return False


def folder_pile_size(state_dir: Path) -> int | None:
    path = state_dir / _STATS_FILE
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                n = data.get("pile_size")
                if isinstance(n, int) and n >= 0:
                    return n
        except (OSError, json.JSONDecodeError):
            pass
    from choice.folder_index import load_index

    idx = load_index(state_dir)
    if idx.ordered:
        return len(idx.ordered)
    return None


def write_folder_stats(state_dir: Path, pile_size: int) -> None:
    path = state_dir / _STATS_FILE
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        from choice.atomic_io import write_json_atomic

        write_json_atomic(path, {"pile_size": pile_size})
    except OSError:
        return


def decided_today(deck: Deck) -> int:
    from choice.act import _choices

    today = datetime.now().astimezone().date()
    count = 0
    for row in _choices(deck).values():
        if row.get("later"):
            continue
        ts = row.get("ts")
        if not isinstance(ts, str):
            continue
        try:
            when = datetime.fromisoformat(ts).astimezone().date()
        except ValueError:
            continue
        if when == today:
            count += 1
    return count


def today_count_label(deck: Deck) -> str | None:
    n = decided_today(deck)
    if n <= 0:
        return None
    word = "decision" if n == 1 else "decisions"
    return f"{n} {word} today"


def public_counts(deck: Deck) -> dict:
    mode = load_counts_mode(deck)
    return {
        "mode": mode,
        "hidden": counts_hidden(deck),
        "default": defaults_for(deck),
    }
