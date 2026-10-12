# SPDX-License-Identifier: AGPL-3.0-only
"""Client-held item ids: keep delivery order stable while the source reorders."""

from __future__ import annotations

_DEFAULT_SIZE = 30
_MAX_HELD = 500


def buffer_size_from_env(default: int = _DEFAULT_SIZE) -> int:
    from choice.env_config import env_int

    return max(1, min(_MAX_HELD, env_int("CHOICE_CLIENT_BUFFER", env_int("CHOICE_BUFFER_SIZE", default))))


def parse_held(raw: str | None, *, limit: int) -> list[str]:
    if not raw or not str(raw).strip():
        return []
    cap = max(1, min(limit, _MAX_HELD))
    out: list[str] = []
    for part in str(raw).split(","):
        item = part.strip()
        if not item or item in out:
            continue
        out.append(item)
        if len(out) >= cap:
            break
    return out


def merge_held_pile(pile: list[str], held: list[str]) -> list[str]:
    """Held ids stay in client order at the front; the rest follow source order."""
    if not held:
        return pile
    pile_set = set(pile)
    head: list[str] = []
    seen: set[str] = set()
    for item_id in held:
        if item_id in seen:
            continue
        if item_id not in pile_set:
            continue
        head.append(item_id)
        seen.add(item_id)
    tail = [rid for rid in pile if rid not in seen]
    return head + tail
