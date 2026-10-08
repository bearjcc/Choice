# SPDX-License-Identifier: AGPL-3.0-only
"""Swipe direction from pointer deltas (mirrors the web UI)."""

from __future__ import annotations


def resolve_swipe(
    dx: float,
    dy: float,
    *,
    arm: float = 10,
    threshold: float = 88,
) -> str | None:
    """Return left, right, up, down, or None if not past threshold."""
    if abs(dx) < arm and abs(dy) < arm:
        return None
    if abs(dx) >= abs(dy):
        if abs(dx) < threshold:
            return None
        return "right" if dx > 0 else "left"
    if abs(dy) < threshold:
        return None
    return "up" if dy < 0 else "down"
