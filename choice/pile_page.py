# SPDX-License-Identifier: AGPL-3.0-only
"""Stable cursor paging over a pile id list."""

from __future__ import annotations


def page_after(pile: list[str], after: str | None, limit: int) -> tuple[list[str], str | None]:
    if limit <= 0:
        limit = len(pile)
    start = 0
    if after:
        try:
            start = pile.index(after) + 1
        except ValueError:
            start = 0
    page = pile[start : start + limit]
    next_after = None
    if page and start + len(page) < len(pile):
        next_after = page[-1]
    return page, next_after
