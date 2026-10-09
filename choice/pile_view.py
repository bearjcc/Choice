# SPDX-License-Identifier: AGPL-3.0-only
"""Filter and sort folder pile ids using index metadata (no rescan)."""

from __future__ import annotations

import hashlib
from pathlib import Path

from choice.bounded_cache import LruDict
from choice.folder_index import FolderIndex, _dir_of, load_index
from choice.load import Deck
from choice.natsort import natural_key
from choice.view_prefs import ViewPrefs, load_view_prefs, pile_view_locked

_view_cache: LruDict[str, list[str]] = LruDict(48)

_VIDEO = frozenset({".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"})


def media_kind(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".gif":
        return "gif"
    if ext in _VIDEO:
        return "video"
    from choice.load import _is_image

    if _is_image(path):
        return "image"
    return "file"


def meta_for(root: Path, rel: str) -> dict:
    path = (root / rel).resolve()
    folder = _dir_of(rel)
    name = Path(rel).name
    try:
        mtime_ns = path.stat().st_mtime_ns
    except OSError:
        mtime_ns = 0
    ext = path.suffix.lower()
    return {
        "mtime_ns": mtime_ns,
        "folder": folder,
        "name": name,
        "ext": ext,
        "kind": media_kind(path),
    }


def ensure_meta(deck: Deck, idx: FolderIndex) -> None:
    root = deck.root.resolve()
    missing = [rid for rid in idx.ordered if rid not in idx.meta]
    if not missing:
        return
    for rid in missing:
        idx.meta[rid] = meta_for(root, rid)


def _stable_random_key(seed: str, rel: str) -> int:
    digest = hashlib.sha256(f"{seed}\0{rel}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _passes_filters(rel: str, meta: dict, prefs: ViewPrefs) -> bool:
    folder = str(meta.get("folder") or _dir_of(rel))
    if prefs.include_folders:
        if not any(folder == inc or folder.startswith(inc + "/") for inc in prefs.include_folders):
            return False
    if prefs.exclude_folders:
        if any(folder == exc or folder.startswith(exc + "/") for exc in prefs.exclude_folders):
            return False
    if not prefs.file_types:
        return True
    want = {t.lower().lstrip(".") for t in prefs.file_types}
    kind = str(meta.get("kind") or "")
    ext = str(meta.get("ext") or "").lstrip(".")
    if kind in want:
        return True
    if ext and ext in want:
        return True
    return False


def view_order_ids(deck: Deck, idx: FolderIndex, prefs: ViewPrefs) -> list[str]:
    if pile_view_locked(deck):
        return list(idx.ordered)
    if prefs.sort_mode == "scan" and not (
        prefs.file_types or prefs.include_folders or prefs.exclude_folders
    ):
        return list(idx.ordered)
    key = f"{deck.state_dir.resolve()}:{idx.generation}:{prefs.fingerprint()}"
    hit = _view_cache.get(key)
    if hit is not None:
        return list(hit)
    ensure_meta(deck, idx)
    seed = prefs.random_seed or deck.id
    rows: list[str] = []
    for rel in idx.ordered:
        meta = idx.meta.get(rel) or meta_for(deck.root.resolve(), rel)
        if not _passes_filters(rel, meta, prefs):
            continue
        rows.append(rel)
    mode = prefs.sort_mode

    def sort_key(rel: str) -> tuple:
        meta = idx.meta.get(rel) or {}
        if mode == "random":
            return (_stable_random_key(seed, rel),)
        if mode == "mtime_desc":
            return (-int(meta.get("mtime_ns") or 0), natural_key(rel))
        if mode == "mtime_asc":
            return (int(meta.get("mtime_ns") or 0), natural_key(rel))
        if mode == "folder":
            folder = str(meta.get("folder") or _dir_of(rel))
            name = str(meta.get("name") or Path(rel).name)
            return (natural_key(folder), natural_key(name))
        if mode == "filename":
            name = str(meta.get("name") or Path(rel).name)
            return (natural_key(name), natural_key(rel))
        return (natural_key(rel),)

    if mode != "scan":
        rows.sort(key=sort_key)
    _view_cache.set(key, list(rows))
    return list(rows)


def filtered_scan_order(deck: Deck) -> list[str]:
    idx = load_index(deck.state_dir)
    prefs = load_view_prefs(deck)
    if pile_view_locked(deck):
        return list(idx.ordered)
    ensure_meta(deck, idx)
    if not any([prefs.file_types, prefs.include_folders, prefs.exclude_folders]):
        return view_order_ids(deck, idx, prefs)
    out: list[str] = []
    for rel in idx.ordered:
        meta = idx.meta.get(rel) or meta_for(deck.root.resolve(), rel)
        if _passes_filters(rel, meta, prefs):
            out.append(rel)
    return out
