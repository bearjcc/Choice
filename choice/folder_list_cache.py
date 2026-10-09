# SPDX-License-Identifier: AGPL-3.0-only
"""Cached folder listings keyed by file count and newest mtime in the tree."""

from __future__ import annotations

from pathlib import Path

from choice.bounded_cache import LruDict
from choice.folder_deck import FolderScanOptions, list_files, match_globs
from choice.load import _is_image

_CACHE = LruDict[tuple, tuple[tuple[int, int], list[Path]]](32)


def invalidate_under(_root: Path) -> None:
    _CACHE.clear()


def _stamp(files: list[Path]) -> tuple[int, int]:
    max_ns = 0
    for path in files:
        try:
            max_ns = max(max_ns, path.stat().st_mtime_ns)
        except OSError:
            continue
    return (len(files), max_ns)


def cached_list_files(
    folder: Path,
    recursive: bool,
    skip_dirs: set[Path],
) -> list[Path]:
    folder = folder.resolve()
    key = (str(folder), recursive, frozenset(str(p) for p in skip_dirs))
    files = list_files(folder, recursive, skip_dirs)
    stamp = _stamp(files)
    hit = _CACHE.get(key)
    if hit is not None and hit[0] == stamp:
        return hit[1]
    _CACHE.set(key, (stamp, files))
    return files


def folder_item_ids(root: Path, scan: FolderScanOptions) -> frozenset[str]:
    skip_dirs = set(scan.sort_dirs(root))
    skip_dirs.add((root / ".choice").resolve())
    files = cached_list_files(root, scan.recursive, skip_dirs)
    ids: set[str] = set()
    for path in files:
        if scan.images_only and not _is_image(path):
            continue
        try:
            rel = path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            rel = path.name
        if not match_globs(rel, path.name, scan.include, scan.exclude):
            continue
        if _under_sort(path, skip_dirs):
            continue
        ids.add(rel)
    return frozenset(ids)


def _under_sort(path: Path, skip_dirs: set[Path]) -> bool:
    resolved = path.resolve()
    for directory in skip_dirs:
        try:
            resolved.relative_to(directory)
            return True
        except ValueError:
            continue
    return False
