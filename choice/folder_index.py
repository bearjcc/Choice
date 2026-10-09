# SPDX-License-Identifier: AGPL-3.0-only
"""Incremental folder index: stable pile order, background scans, fast counts."""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from choice.bounded_cache import LruDict
from choice.deck_index import plugin_pile_counts
from choice.folder_deck import FolderScanOptions, match_globs
from choice.load import Deck, Item, _hidden, _is_image, _mtime, _size_text, inside

_INDEX_FILE = "folder_index.json"
_DEBOUNCE = 1.5
_mem: LruDict[str, FolderIndex] = LruDict(32)
_timers: dict[str, threading.Timer] = {}
_timer_lock = threading.Lock()
_scan_locks: LruDict[str, threading.Lock] = LruDict(32)


@dataclass
class FolderIndex:
    ordered: list[str] = field(default_factory=list)
    dir_mtimes: dict[str, int] = field(default_factory=dict)
    generation: int = 0
    updated_at: float = 0.0
    scanning: bool = False
    stale: bool = True

    def to_dict(self) -> dict:
        return {
            "ordered": self.ordered,
            "dir_mtimes": self.dir_mtimes,
            "generation": self.generation,
            "updated_at": self.updated_at,
            "stale": self.stale,
        }

    @staticmethod
    def from_dict(data: dict) -> FolderIndex:
        ordered = data.get("ordered")
        if not isinstance(ordered, list):
            ordered = []
        mtimes = data.get("dir_mtimes")
        if not isinstance(mtimes, dict):
            mtimes = {}
        return FolderIndex(
            ordered=[str(x) for x in ordered if x],
            dir_mtimes={str(k): int(v) for k, v in mtimes.items()},
            generation=int(data.get("generation") or 0),
            updated_at=float(data.get("updated_at") or 0),
            stale=bool(data.get("stale", True)),
        )


def index_path(state_dir: Path) -> Path:
    return state_dir / _INDEX_FILE


def generation(state_dir: Path) -> int:
    return load_index(state_dir).generation


def load_index(state_dir: Path) -> FolderIndex:
    key = str(state_dir.resolve())
    hit = _mem.get(key)
    if hit is not None:
        return hit
    path = index_path(state_dir)
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                idx = FolderIndex.from_dict(data)
                _mem.set(key, idx)
                return idx
        except (OSError, json.JSONDecodeError):
            pass
    idx = FolderIndex()
    _mem.set(key, idx)
    return idx


def save_index(state_dir: Path, idx: FolderIndex) -> None:
    key = str(state_dir.resolve())
    idx.updated_at = time.time()
    _mem.set(key, idx)
    path = index_path(state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(idx.to_dict()), encoding="utf-8")
    tmp.replace(path)


def schedule_scan(deck: Deck) -> None:
    if deck.folder_scan is None:
        return
    key = str(deck.state_dir.resolve())

    def _fire():
        scan_incremental(deck)

    with _timer_lock:
        old = _timers.pop(key, None)
        if old:
            old.cancel()
        timer = threading.Timer(_DEBOUNCE, _fire)
        _timers[key] = timer
        timer.daemon = True
        timer.start()


def scan_incremental(deck: Deck) -> None:
    if deck.folder_scan is None:
        return
    key = str(deck.state_dir.resolve())
    lock = _scan_locks.get(key)
    if lock is None:
        lock = threading.Lock()
        _scan_locks.set(key, lock)
    if not lock.acquire(blocking=False):
        schedule_scan(deck)
        return
    try:
        _scan_locked(deck)
    finally:
        lock.release()


def _scan_locked(deck: Deck) -> None:
    scan = deck.folder_scan
    assert scan is not None
    root = deck.root.resolve()
    state_dir = deck.state_dir
    idx = load_index(state_dir)
    idx.scanning = True
    save_index(state_dir, idx)
    skip_dirs = set(scan.sort_dirs(root))
    skip_dirs.add((root / ".choice").resolve())
    known = set(idx.ordered)
    changed = False
    for dir_path, dir_rel in _iter_dirs(root, scan.recursive, skip_dirs):
        try:
            mtime = dir_path.stat().st_mtime_ns
        except OSError:
            continue
        prev = idx.dir_mtimes.get(dir_rel)
        if prev is not None and prev == mtime:
            continue
        idx.dir_mtimes[dir_rel] = mtime
        seen_here: set[str] = set()
        try:
            with os.scandir(dir_path) as it:
                for entry in it:
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    path = Path(entry.path)
                    if path.is_symlink():
                        continue
                    if path.name.startswith(".") or _hidden(path, root):
                        continue
                    rel = _relative(root, path)
                    if _under_sort(path, skip_dirs) or not _passes(
                        scan, root, path, rel, skip_dirs
                    ):
                        continue
                    seen_here.add(rel)
                    if rel not in known:
                        idx.ordered.append(rel)
                        known.add(rel)
                        changed = True
        except OSError:
            continue
        gone = [rid for rid in idx.ordered if _dir_of(rid) == dir_rel and rid not in seen_here]
        if gone:
            idx.ordered = [rid for rid in idx.ordered if rid not in gone]
            known -= set(gone)
            changed = True
    if changed:
        idx.generation += 1
    idx.stale = False
    idx.scanning = False
    save_index(state_dir, idx)


def apply_move(state_dir: Path, from_rel: str, to_rel: str, *, reverse: bool = False) -> None:
    if reverse:
        from_rel, to_rel = to_rel, from_rel
    idx = load_index(state_dir)
    if from_rel in idx.ordered:
        pos = idx.ordered.index(from_rel)
        idx.ordered[pos] = to_rel
        idx.generation += 1
        idx.stale = False
        save_index(state_dir, idx)


def summary(deck: Deck, log_decided: set[str]) -> dict:
    idx = load_index(deck.state_dir)
    outdated = _tree_dirs_changed(deck, idx)
    if not idx.ordered and not idx.scanning:
        schedule_scan(deck)
    elif idx.stale or idx.scanning or outdated:
        schedule_scan(deck)
    universe = frozenset(idx.ordered)
    total, decided, left, list_size = plugin_pile_counts(log_decided, universe, frozenset())
    return {
        "ok": True,
        "total": total,
        "decided": decided,
        "left": left,
        "list_size": list_size if idx.ordered else None,
        "meter": True,
        "stale": idx.stale or idx.scanning or outdated or not idx.ordered,
    }


def _tree_dirs_changed(deck: Deck, idx: FolderIndex) -> bool:
    scan = deck.folder_scan
    if scan is None:
        return False
    root = deck.root.resolve()
    skip_dirs = set(scan.sort_dirs(root))
    skip_dirs.add((root / ".choice").resolve())
    for dir_path, dir_rel in _iter_dirs(root, scan.recursive, skip_dirs):
        try:
            mtime = dir_path.stat().st_mtime_ns
        except OSError:
            continue
        if idx.dir_mtimes.get(dir_rel) != mtime:
            return True
    return False


def progress_page(
    deck: Deck,
    choices: dict,
    pending: bool,
    offset: int,
    limit: int,
) -> tuple[list[str], int, int, int, list[str]]:
    """Return page ids, total, decided, left, warnings."""
    scan = deck.folder_scan
    assert scan is not None
    idx = load_index(deck.state_dir)
    if not idx.ordered and not idx.scanning:
        scan_incremental(deck)
        idx = load_index(deck.state_dir)
    else:
        schedule_scan(deck)
    warnings: list[str] = []
    if not idx.ordered:
        return [], 0, 0, 0, warnings
    pile: list[str] = []
    decided = 0
    for rid in idx.ordered:
        choice = choices.get(rid)
        log_done = choice is not None and not choice.get("later")
        if log_done:
            decided += 1
            if pending:
                continue
        pile.append(rid)
    total = len(idx.ordered)
    left = len(pile)
    if limit <= 0:
        limit = min(200, len(pile))
    page = pile[offset : offset + limit]
    return page, total, decided, left, warnings


def item_for_id(deck: Deck, rel_id: str) -> Item | None:
    scan = deck.folder_scan
    if scan is None:
        return None
    path = (deck.root / rel_id).resolve()
    if not path.is_file() or not inside(deck.root, path):
        return None
    kind = "image" if _is_image(path) else "file"
    title = path.name
    body = _size_text(path) if kind == "file" else ""
    if path.suffix.lower() == ".heic":
        kind = "file"
        body = "HEIC photo. Choice will not preview it. A decision still applies to the file."
    return Item(
        id=rel_id,
        kind=kind,
        title=title,
        body=body,
        path=path,
        media_token=str(_mtime(path)),
        fields={"file": rel_id},
    )


def load_deck_items(deck: Deck) -> tuple[list[Item], list[str]]:
    idx = load_index(deck.state_dir)
    if not idx.ordered and not idx.scanning:
        scan_incremental(deck)
        idx = load_index(deck.state_dir)
    else:
        schedule_scan(deck)
    items: list[Item] = []
    for rid in idx.ordered:
        item = item_for_id(deck, rid)
        if item is not None:
            items.append(item)
    return items, []


def load_items_for(
    root: Path, state_dir: Path, scan: FolderScanOptions
) -> tuple[list[Item], list[str]]:
    deck = Deck(
        id="",
        title="",
        root=root.resolve(),
        state_dir=state_dir,
        directions={},
        buttons=[],
        blind=False,
        warnings=[],
        folder_scan=scan,
        _load=None,
    )
    return load_deck_items(deck)


def _iter_dirs(root: Path, recursive: bool, skip_dirs: set[Path]):
    root = root.resolve()
    skip = {d.resolve() for d in skip_dirs}

    def skip_tree(path: Path) -> bool:
        for parent in [path, *path.parents]:
            if parent in skip:
                return True
        return False

    if not recursive:
        yield root, "."
        return
    for dirpath, dirnames, _files in os.walk(root, topdown=True):
        current = Path(dirpath)
        if skip_tree(current):
            dirnames[:] = []
            continue
        dirnames[:] = [
            name
            for name in dirnames
            if not name.startswith(".") and (current / name).resolve() not in skip
        ]
        try:
            rel = current.relative_to(root).as_posix()
        except ValueError:
            rel = "."
        if rel == "":
            rel = "."
        yield current, rel


def _relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


def _dir_of(rel_id: str) -> str:
    if "/" not in rel_id:
        return "."
    return rel_id.rsplit("/", 1)[0]


def _passes(
    scan: FolderScanOptions,
    root: Path,
    path: Path,
    rel: str,
    skip_dirs: set[Path],
) -> bool:
    if scan.images_only and not _is_image(path):
        return False
    if not match_globs(rel, path.name, scan.include, scan.exclude):
        return False
    resolved = path.resolve()
    for directory in skip_dirs:
        try:
            resolved.relative_to(directory)
            return False
        except ValueError:
            continue
    return True


def _under_sort(path: Path, skip_dirs: set[Path]) -> bool:
    resolved = path.resolve()
    for directory in skip_dirs:
        try:
            resolved.relative_to(directory)
            return True
        except ValueError:
            continue
    return False
