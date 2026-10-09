# SPDX-License-Identifier: AGPL-3.0-only
"""Reserve sort destinations against disk and the work queue."""

from __future__ import annotations

from pathlib import Path

from choice.load import Deck, Item, inside


def preferred_dest_rel(deck: Deck, item: Item, into: str) -> str:
    if item.path is None:
        raise ValueError("no file")
    dest_root = (deck.root / into).resolve()
    if not inside(deck.root, dest_root):
        raise ValueError("into outside deck")
    rel = item.path.resolve().relative_to(deck.root.resolve())
    into_norm = into.replace("\\", "/")
    if "/" in into_norm or into_norm.startswith("."):
        dest = (dest_root / rel).resolve()
    else:
        dest = (dest_root / rel.name).resolve()
    if not inside(deck.root, dest):
        raise ValueError("dest outside deck")
    return dest.relative_to(deck.root.resolve()).as_posix()


def taken_destinations(jobs, root: Path) -> set[str]:
    out: set[str] = set()
    for job in jobs:
        if job.status not in {"pending", "running"}:
            continue
        if job.kind != "file" or not job.file_op:
            continue
        to_rel = str(job.file_op.get("to") or "").replace("\\", "/")
        if to_rel:
            out.add(to_rel)
    return out


def allocate_dest_rel(root: Path, preferred_rel: str, taken: set[str]) -> str:
    preferred_rel = preferred_rel.replace("\\", "/")
    base = (root / preferred_rel).resolve()
    if not inside(root, base):
        raise ValueError("bad dest")
    candidate = base
    n = 0
    while n < 10_000:
        rel = candidate.relative_to(root.resolve()).as_posix()
        if rel not in taken and not candidate.exists():
            taken.add(rel)
            return rel
        n += 1
        candidate = base.parent / f"{base.stem}_{n}{base.suffix}"
    raise RuntimeError(f"no free name near {preferred_rel}")


def replan_dest_rel(root: Path, from_rel: str, op: dict, jobs) -> str:
    preferred = str(op.get("to") or "").replace("\\", "/")
    if not preferred:
        preferred = from_rel
    taken = taken_destinations(jobs, root)
    return allocate_dest_rel(root, preferred, taken)
