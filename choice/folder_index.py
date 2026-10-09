# SPDX-License-Identifier: AGPL-3.0-only
"""Incremental folder index: stable pile order, background scans, fast counts."""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from choice.atomic_io import atomic_replace
from choice.bounded_cache import LruDict
from choice.deck_index import plugin_pile_counts
from choice.folder_deck import FolderScanOptions, match_globs
from choice.load import Deck, Item, _hidden, _is_image, _mtime, _size_text, inside

_INDEX_FILE = "folder_index.json"
_META_FILE = "folder_meta.json"
_DEBOUNCE = 1.5
_mem: LruDict[str, FolderIndex] = LruDict(32)
_timers: dict[str, threading.Timer] = {}
_timer_lock = threading.Lock()
_scan_locks: LruDict[str, threading.Lock] = LruDict(32)
_index_mutate_locks: LruDict[str, threading.Lock] = LruDict(32)


@dataclass
class FolderIndex:
    ordered: list[str] = field(default_factory=list)
    dir_mtimes: dict[str, int] = field(default_factory=dict)
    meta: dict[str, dict] = field(default_factory=dict)
    generation: int = 0
    updated_at: float = 0.0
    scanning: bool = False
    stale: bool = True
    pending_front: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        out = {
            "ordered": self.ordered,
            "dir_mtimes": self.dir_mtimes,
            "generation": self.generation,
            "updated_at": self.updated_at,
            "stale": self.stale,
        }
        if self.pending_front:
            out["pending_front"] = list(self.pending_front)
        return out

    @staticmethod
    def from_dict(data: dict) -> FolderIndex:
        ordered = data.get("ordered")
        if not isinstance(ordered, list):
            ordered = []
        mtimes = data.get("dir_mtimes")
        if not isinstance(mtimes, dict):
            mtimes = {}
        meta = data.get("meta")
        if not isinstance(meta, dict):
            meta = {}
        clean_meta: dict[str, dict] = {}
        for k, v in meta.items():
            if isinstance(v, dict):
                clean_meta[str(k)] = dict(v)
        front = data.get("pending_front")
        if not isinstance(front, list):
            front = []
        return FolderIndex(
            ordered=[str(x) for x in ordered if x],
            dir_mtimes={str(k): int(v) for k, v in mtimes.items()},
            meta=clean_meta,
            generation=int(data.get("generation") or 0),
            updated_at=float(data.get("updated_at") or 0),
            stale=bool(data.get("stale", True)),
            pending_front=[str(x) for x in front if x],
        )


def index_path(state_dir: Path) -> Path:
    return state_dir / _INDEX_FILE


def meta_path(state_dir: Path) -> Path:
    return state_dir / _META_FILE


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
                _load_meta_file(state_dir, idx)
                _mem.set(key, idx)
                return idx
        except (OSError, json.JSONDecodeError):
            pass
    idx = FolderIndex()
    _mem.set(key, idx)
    return idx


def save_index(state_dir: Path, idx: FolderIndex, *, save_meta: bool = False) -> None:
    key = str(state_dir.resolve())
    idx.updated_at = time.time()
    _mem.set(key, idx)
    path = index_path(state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(idx.to_dict()), encoding="utf-8")
    atomic_replace(tmp, path)
    if save_meta:
        _save_meta_file(state_dir, idx)
    from choice.count_prefs import write_folder_stats

    write_folder_stats(state_dir, len(idx.ordered))


def _load_meta_file(state_dir: Path, idx: FolderIndex) -> None:
    path = meta_path(state_dir)
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                idx.meta = {str(k): dict(v) for k, v in data.items() if isinstance(v, dict)}
                return
        except (OSError, json.JSONDecodeError):
            pass
    embedded = idx.meta
    if embedded:
        _save_meta_file(state_dir, idx)


def _save_meta_file(state_dir: Path, idx: FolderIndex) -> None:
    path = meta_path(state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(idx.meta), encoding="utf-8")
    atomic_replace(tmp, path)


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
        in_dir = sum(1 for rid in idx.ordered if _dir_of(rid) == dir_rel)
        try:
            n_files = sum(
                1 for e in os.scandir(dir_path) if e.is_file(follow_symlinks=False)
            )
        except OSError:
            n_files = -1
        if prev is not None and prev == mtime and in_dir == n_files and n_files >= 0:
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
                        from choice.pile_view import meta_for

                        idx.meta[rel] = meta_for(root, rel)
                        changed = True
        except OSError:
            continue
        gone = [rid for rid in idx.ordered if _dir_of(rid) == dir_rel and rid not in seen_here]
        if gone:
            idx.ordered = [rid for rid in idx.ordered if rid not in gone]
            for rid in gone:
                idx.meta.pop(rid, None)
            known -= set(gone)
            changed = True
    purged = _purge_sorted_from_index(idx, root, skip_dirs)
    if purged:
        changed = True
    if changed:
        idx.generation += 1
    idx.stale = False
    idx.scanning = False
    save_index(state_dir, idx, save_meta=changed)


def _pin_pending_front(idx: FolderIndex, rel: str) -> None:
    if not rel:
        return
    idx.pending_front = [rel] + [r for r in idx.pending_front if r != rel]


def _unpin_pending_front(idx: FolderIndex, rel: str) -> None:
    if not rel:
        return
    idx.pending_front = [r for r in idx.pending_front if r != rel]


def _index_mutate_lock(state_dir: Path) -> threading.Lock:
    key = str(state_dir.resolve())
    lock = _index_mutate_locks.get(key)
    if lock is None:
        lock = threading.Lock()
        _index_mutate_locks.set(key, lock)
    return lock


def _readmit_to_pile_front(idx: FolderIndex, rel: str) -> bool:
    if not rel:
        return False
    changed = False
    if rel in idx.ordered:
        if idx.ordered[0] != rel:
            idx.ordered = [rel] + [r for r in idx.ordered if r != rel]
            changed = True
    else:
        idx.ordered.insert(0, rel)
        changed = True
    if rel not in idx.pending_front or idx.pending_front[0] != rel:
        _pin_pending_front(idx, rel)
        changed = True
    return changed


def apply_pending_front(idx: FolderIndex, pile: list[str]) -> list[str]:
    if not idx.pending_front:
        return pile
    front = [r for r in idx.pending_front if r in pile]
    if not front:
        return pile
    seen = set(front)
    return front + [r for r in pile if r not in seen]


def apply_move(
    state_dir: Path,
    from_rel: str,
    to_rel: str,
    *,
    reverse: bool = False,
    deck: Deck | None = None,
) -> None:
    with _index_mutate_lock(state_dir):
        idx = load_index(state_dir)
        touched: list[str] = []
        if reverse:
            if from_rel and _readmit_to_pile_front(idx, from_rel):
                touched = [from_rel]
                idx.generation += 1
                idx.stale = False
                if deck is not None:
                    _refresh_dir_mtimes(deck, idx, touched)
                save_index(state_dir, idx)
            return
        if from_rel in idx.ordered:
            _unpin_pending_front(idx, from_rel)
            idx.ordered = [rid for rid in idx.ordered if rid != from_rel]
            touched = [from_rel]
            if to_rel:
                touched.append(to_rel)
            idx.generation += 1
            idx.stale = False
            if deck is not None:
                _refresh_dir_mtimes(deck, idx, touched)
            save_index(state_dir, idx)


def _refresh_dir_mtimes(deck: Deck, idx: FolderIndex, rels: list[str]) -> None:
    if deck.folder_scan is None:
        return
    root = deck.root.resolve()
    dirs: set[str] = set()
    for rel in rels:
        if rel:
            dirs.add(_dir_of(rel))
    for dir_rel in dirs:
        path = root if dir_rel == "." else (root / dir_rel)
        try:
            idx.dir_mtimes[dir_rel] = path.stat().st_mtime_ns
        except OSError:
            continue


def readmit_path(state_dir: Path, rel: str, *, deck: Deck | None = None) -> bool:
    """Put a source path back on the pile when a sort move did not land."""
    if not rel:
        return False
    with _index_mutate_lock(state_dir):
        idx = load_index(state_dir)
        if not _readmit_to_pile_front(idx, rel):
            return False
        idx.generation += 1
        idx.stale = False
        if deck is not None:
            _refresh_dir_mtimes(deck, idx, [rel])
        save_index(state_dir, idx)
        return True


def kick_background_scan(deck: Deck) -> None:
    """Start an incremental scan without waiting on the debounced timer."""
    if deck.folder_scan is None:
        return
    idx = load_index(deck.state_dir)
    if idx.scanning:
        return

    def _run() -> None:
        scan_incremental(deck)

    threading.Thread(
        target=_run,
        name=f"folder-scan-{deck.id}",
        daemon=True,
    ).start()


def _purge_sorted_from_index(idx: FolderIndex, root: Path, skip_dirs: set[Path]) -> bool:
    kept: list[str] = []
    changed = False
    for rid in idx.ordered:
        path = (root / rid).resolve()
        if _under_sort(path, skip_dirs):
            changed = True
            continue
        kept.append(rid)
    if changed:
        idx.ordered = kept
    return changed


def summary(deck: Deck, log_decided: set[str], *, counts_hidden: bool = False) -> dict:
    if counts_hidden:
        from choice.count_prefs import today_count_label

        return {
            "ok": True,
            "total": None,
            "decided": len(log_decided),
            "left": None,
            "list_size": None,
            "meter": False,
            "counts_hidden": True,
            "count_label": today_count_label(deck),
        }
    idx = load_index(deck.state_dir)
    outdated = _tree_dirs_changed(deck, idx)
    if not idx.ordered and not idx.scanning:
        kick_background_scan(deck)
    elif not idx.scanning and (idx.stale or outdated):
        schedule_scan(deck)
    warming = idx.scanning or outdated or idx.stale
    if idx.ordered:
        universe = frozenset(idx.ordered)
        total, decided, left, list_size = plugin_pile_counts(
            log_decided, universe, frozenset()
        )
        label = None
        if warming:
            label = f"{left} left · scanning"
        return {
            "ok": True,
            "total": total,
            "decided": decided,
            "left": left,
            "list_size": list_size,
            "meter": True,
            "stale": warming,
            "count_label": label,
        }
    return {
        "ok": True,
        "total": None,
        "decided": len(log_decided),
        "left": None,
        "list_size": None,
        "meter": False,
        "stale": warming,
        "count_label": "Scanning…" if warming else None,
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
    outdated = _tree_dirs_changed(deck, idx)
    if not idx.ordered and not idx.scanning:
        scan_incremental(deck)
        idx = load_index(deck.state_dir)
    elif not idx.scanning and (idx.stale or outdated):
        schedule_scan(deck)
    warnings: list[str] = []
    if not idx.ordered:
        return [], 0, 0, 0, warnings
    from choice.pile_view import view_order_ids
    from choice.view_prefs import load_view_prefs

    prefs = load_view_prefs(deck)
    ordered = view_order_ids(deck, idx, prefs)
    pile: list[str] = []
    decided = 0
    for rid in ordered:
        choice = choices.get(rid)
        log_done = choice is not None and not choice.get("later")
        if log_done:
            decided += 1
            if pending:
                continue
        pile.append(rid)
    pile = apply_pending_front(idx, pile)
    total = len(ordered)
    left = len(pile)
    if limit <= 0:
        limit = min(200, len(pile))
    page = pile[offset : offset + limit]
    return page, total, decided, left, warnings


def admit_if_on_disk(deck: Deck, item_id: str) -> bool:
    """O(1) add one new file to the index when it already exists on disk."""
    scan = deck.folder_scan
    if scan is None:
        return False
    idx = load_index(deck.state_dir)
    if item_id in idx.ordered:
        return True
    root = deck.root.resolve()
    skip_dirs = set(scan.sort_dirs(root))
    skip_dirs.add((root / ".choice").resolve())
    path = (root / item_id).resolve()
    if not path.is_file() or not inside(root, path):
        return False
    rel = _relative(root, path)
    if _under_sort(path, skip_dirs) or not _passes(scan, root, path, rel, skip_dirs):
        return False
    from choice.pile_view import meta_for

    idx.ordered.append(rel)
    idx.meta[rel] = meta_for(root, rel)
    idx.generation += 1
    idx.stale = False
    save_index(deck.state_dir, idx, save_meta=True)
    return True


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
    outdated = _tree_dirs_changed(deck, idx)
    if not idx.ordered and not idx.scanning:
        scan_incremental(deck)
        idx = load_index(deck.state_dir)
    elif not idx.scanning and (idx.stale or outdated):
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
