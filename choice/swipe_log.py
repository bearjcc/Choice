# SPDX-License-Identifier: AGPL-3.0-only
"""Read Swipe event logs (read-only) and import into Choice decisions."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from choice.load import Deck


def read_events(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def replay_decisions(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Net swipe per item_id (Swipe server.py _apply semantics)."""
    live: list[dict[str, Any]] = []
    per_item: dict[str, list[dict[str, Any]]] = {}
    decided: dict[str, dict[str, Any]] = {}

    def set_dec(item_id: str, swipe: dict[str, Any] | None) -> None:
        if swipe is None:
            decided.pop(item_id, None)
        else:
            decided[item_id] = swipe

    for event in events:
        kind = event.get("type")
        if kind == "swipe" and event.get("item_id"):
            live.append(event)
            per_item.setdefault(str(event["item_id"]), []).append(event)
            set_dec(str(event["item_id"]), event)
            continue
        if kind != "undo" or not event.get("ok"):
            continue
        ref = event.get("ref")
        for index in range(len(live) - 1, -1, -1):
            swipe = live[index]
            if swipe.get("seq") != ref:
                continue
            item_id = str(swipe.get("item_id") or "")
            del live[index]
            lst = [row for row in per_item.get(item_id, []) if row is not swipe]
            if lst:
                per_item[item_id] = lst
            else:
                per_item.pop(item_id, None)
            set_dec(item_id, lst[-1] if lst else None)
            break
    return decided


def swipe_to_choice_record(deck: Deck, swipe: dict[str, Any]) -> dict[str, Any]:
    action_id = str(swipe.get("action") or "")
    action = deck.action(action_id)
    label = action.label if action else action_id
    value = action.value if action else action_id
    later = bool(action.later) if action else False
    seq = swipe.get("seq")
    return {
        "type": "decision",
        "id": f"swipe:{seq}",
        "item": str(swipe.get("item_id") or ""),
        "direction": action_id,
        "value": value,
        "label": label,
        "later": later,
        "note": str(swipe.get("note") or ""),
        "ts": swipe.get("ts") or "",
        "swipe_seq": seq,
        "undo_token": swipe.get("undo_token"),
        "source": "swipe",
    }


def choices_from_swipe_log(deck: Deck, path: Path) -> dict[str, dict[str, Any]]:
    events = read_events(path)
    out: dict[str, dict[str, Any]] = {}
    for swipe in replay_decisions(events).values():
        item_id = str(swipe.get("item_id") or "")
        if not item_id:
            continue
        out[item_id] = swipe_to_choice_record(deck, swipe)
    return out


def merge_swipe_and_choice(
    swipe: dict[str, dict[str, Any]], choice: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    merged = dict(swipe)
    merged.update(choice)
    return merged


def swipe_remaining_count(item_ids: set[str], events: list[dict[str, Any]]) -> int:
    decided = replay_decisions(events)
    done = len(item_ids & set(decided))
    return len(item_ids) - done


def import_events(
    deck: Deck,
    path: Path,
    read_log: Callable[[], list[dict[str, Any]]],
    append: Callable[[Deck, dict[str, Any]], None],
) -> tuple[int, int]:
    """Translate Swipe log lines into Choice log lines."""
    events = read_events(path)
    existing = _existing_import_keys(read_log())
    added = 0
    skipped = 0
    for event in events:
        kind = event.get("type")
        if kind == "swipe":
            seq = event.get("seq")
            key = f"swipe:{seq}"
            if key in existing["decision"]:
                skipped += 1
                continue
            append(deck, swipe_to_choice_record(deck, event))
            existing["decision"].add(key)
            added += 1
            continue
        if kind == "undo" and event.get("ok"):
            ref = f"swipe:{event.get('ref')}"
            if ref in existing["undo_ref"]:
                skipped += 1
                continue
            if ref not in existing["decision"]:
                skipped += 1
                continue
            append(
                deck,
                {
                    "type": "undo",
                    "ref": ref,
                    "item": str(event.get("item_id") or ""),
                    "ts": event.get("ts") or "",
                    "source": "swipe",
                },
            )
            existing["undo_ref"].add(ref)
            added += 1
    return added, skipped


def _existing_import_keys(rows: list[dict[str, Any]]) -> dict[str, set[str]]:
    decision: set[str] = set()
    undo_ref: set[str] = set()
    for row in rows:
        if row.get("type") == "decision" and row.get("id"):
            decision.add(str(row["id"]))
        if row.get("type") == "undo" and row.get("ref"):
            undo_ref.add(str(row["ref"]))
    return {"decision": decision, "undo_ref": undo_ref}
