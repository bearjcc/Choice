# SPDX-License-Identifier: AGPL-3.0-only
"""Glicko-2 style ratings and informative pair selection for large sets."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass


@dataclass
class Player:
    id: str
    rating: float = 1500.0
    rd: float = 350.0
    vol: float = 0.06


def pick_pair(players: dict[str, Player], decided: set[tuple[str, str]]) -> tuple[str, str] | None:
    """Choose the pair whose outcome would shrink uncertainty the most."""
    ids = list(players.keys())
    if len(ids) < 2:
        return None
    best: tuple[str, str] | None = None
    best_score = -1.0
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            key = tuple(sorted((a, b)))
            if key in decided:
                continue
            pa, pb = players[a], players[b]
            score = min(pa.rd, pb.rd) + abs(pa.rating - pb.rating) * 0.01
            if score > best_score:
                best_score = score
                best = (a, b)
    if best:
        return best
    # All pairs seen: random tie-break
    a, b = random.sample(ids, 2)
    return a, b


def update(players: dict[str, Player], winner: str, loser: str) -> None:
    pw = players[winner]
    pl = players[loser]
    _glicko_update(pw, pl, 1.0)
    _glicko_update(pl, pw, 0.0)


def ranking(players: dict[str, Player]) -> list[tuple[str, float, float]]:
    rows = [(pid, p.rating, p.rd) for pid, p in players.items()]
    rows.sort(key=lambda r: (-r[1], r[2]))
    return rows


def confidence(players: dict[str, Player], top_n: int = 10, stable_rounds: int = 3) -> float:
    """0..1 progress estimate from rating deviation shrinkage."""
    if not players:
        return 0.0
    rows = ranking(players)
    top = rows[: min(top_n, len(rows))]
    if not top:
        return 0.0
    avg_rd = sum(r[2] for r in top) / len(top)
    return max(0.0, min(1.0, 1.0 - avg_rd / 350.0))


def _glicko_update(player: Player, opponent: Player, score: float) -> None:
    """One-step Glicko-2 simplified update (rating + RD only)."""
    q = math.log(10) / 400
    g = 1 / math.sqrt(1 + 3 * q * q * opponent.rd * opponent.rd / (math.pi * math.pi))
    exp = 1 / (1 + 10 ** (-g * (player.rating - opponent.rating) / 400))
    d_sq = 1 / (q * q * g * g * exp * (1 - exp) + 1e-9)
    player.rating += q / (1 / (player.rd * player.rd) + 1 / d_sq) * g * (score - exp)
    player.rd = math.sqrt(1 / (1 / (player.rd * player.rd) + 1 / d_sq))
