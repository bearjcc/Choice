# SPDX-License-Identifier: AGPL-3.0-only
"""Folder pile scanning: results vs sort output, recursion, globs, sort targets."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path

from choice.load import (
    SKIP_NAMES,
    Deck,
    DeckProblem,
    Direction,
    Item,
    _file_directions,
    _hidden,
    _is_image,
    _mtime,
    _size_text,
    inside,
)

_OUTPUT = frozenset({"results", "sort"})


@dataclass
class FolderScanOptions:
    output: str = "results"
    recursive: bool = False
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    sort_targets: dict[str, str] = field(default_factory=dict)
    images_only: bool = False

    def sort_dirs(self, root: Path) -> list[Path]:
        dirs: list[Path] = []
        for name in self.sort_targets.values():
            if not name or name.startswith(".."):
                continue
            target = (root / name).resolve()
            if inside(root, target):
                dirs.append(target)
        return dirs


def parse_folder_options(raw: dict | None) -> FolderScanOptions:
    raw = raw or {}
    output = str(raw.get("output") or raw.get("output_mode") or "results").strip().lower()
    if output not in _OUTPUT:
        raise DeckProblem("output must be results or sort.")
    recursive = bool(raw.get("recursive"))
    include = _glob_list(raw.get("include") or raw.get("include_globs"))
    exclude = _glob_list(raw.get("exclude") or raw.get("exclude_globs"))
    sort_targets = _parse_sort_targets(raw)
    images_only = str(raw.get("type") or "").lower() == "images"
    return FolderScanOptions(
        output=output,
        recursive=recursive,
        include=include,
        exclude=exclude,
        sort_targets=sort_targets,
        images_only=images_only,
    )


def merge_folder_options(source: dict, deck_options: dict) -> FolderScanOptions:
    merged = dict(source)
    for key, value in deck_options.items():
        if key in {
            "output",
            "output_mode",
            "recursive",
            "include",
            "exclude",
            "include_globs",
            "exclude_globs",
            "sort",
            "sort_targets",
            "type",
        } or key.startswith("sort_"):
            merged[key] = value
    return parse_folder_options(merged)


def wire_sort_directions(
    directions: dict[str, Direction], targets: dict[str, str]
) -> dict[str, Direction]:
    out: dict[str, Direction] = {}
    for key, direction in directions.items():
        folder = targets.get(key)
        if folder:
            out[key] = Direction(
                id=direction.id,
                label=direction.label,
                value=direction.value,
                later=direction.later,
                does="move",
                into=folder,
                color=direction.color,
            )
        elif direction.does in {"move", "copy"} and direction.into:
            out[key] = direction
        else:
            out[key] = Direction(
                id=direction.id,
                label=direction.label,
                value=direction.value,
                later=direction.later,
                does="label",
                into=None,
                color=direction.color,
            )
    return out


def wire_sort_buttons(buttons: list[Direction], targets: dict[str, str]) -> list[Direction]:
    out: list[Direction] = []
    for direction in buttons:
        folder = targets.get(direction.id)
        if folder:
            out.append(
                Direction(
                    id=direction.id,
                    label=direction.label,
                    value=direction.value,
                    later=direction.later,
                    does="move",
                    into=folder,
                    color=direction.color,
                )
            )
        else:
            out.append(direction)
    return out


def default_results_directions() -> dict[str, Direction]:
    raw = _file_directions()
    out: dict[str, Direction] = {}
    for key, spec in raw.items():
        out[key] = Direction(
            id=key,
            label=spec["label"],
            value=spec["value"],
            later=bool(spec.get("later")),
            does="label",
            into=None,
            color=spec.get("color"),
        )
    return out


def build_file_deck(
    folder: Path,
    deck_id: str,
    title: str,
    state_dir: Path,
    options: dict,
) -> Deck:
    scan = parse_folder_options(options)
    if scan.output == "sort" and not scan.sort_targets:
        scan.sort_targets = {
            "right": str(options.get("sort_right") or "keep"),
            "left": str(options.get("sort_left") or "delete"),
        }
    directions = default_results_directions()
    if scan.output == "sort":
        directions = wire_sort_directions(directions, scan.sort_targets)
    deck = Deck(
        id=deck_id,
        title=title,
        root=folder.resolve(),
        state_dir=state_dir,
        directions=directions,
        buttons=[],
        blind=False,
        warnings=[],
        folder_scan=scan,
        _load=lambda: (items_from_folder_scan(folder.resolve(), folder.resolve(), scan), []),
    )
    return deck


def items_from_folder_scan(root: Path, folder: Path, scan: FolderScanOptions) -> list[Item]:
    from choice.folder_list_cache import cached_list_files

    skip_dirs = set(scan.sort_dirs(root))
    skip_dirs.add((root / ".choice").resolve())
    files = cached_list_files(folder, scan.recursive, skip_dirs)
    items: list[Item] = []
    for path in files:
        if scan.images_only and not _is_image(path):
            continue
        rel_posix = _relative_posix(root, path)
        if not match_globs(rel_posix, path.name, scan.include, scan.exclude):
            continue
        if _under_sort_dir(path, skip_dirs):
            continue
        kind = "image" if _is_image(path) else "file"
        title = path.name
        body = _size_text(path) if kind == "file" else ""
        if path.suffix.lower() == ".heic":
            kind = "file"
            body = "HEIC photo. Choice will not preview it. A decision still applies to the file."
        items.append(
            Item(
                id=rel_posix,
                kind=kind,
                title=title,
                body=body,
                path=path.resolve(),
                media_token=str(_mtime(path)),
                fields={"file": rel_posix},
            )
        )
    items.sort(key=lambda item: item.id.lower())
    return items


def list_files(folder: Path, recursive: bool, skip_dirs: set[Path]) -> list[Path]:
    folder = folder.resolve()
    skip = {d.resolve() for d in skip_dirs}

    def skip_tree(path: Path) -> bool:
        for parent in [path, *path.parents]:
            if parent in skip:
                return True
        return False

    out: list[Path] = []
    if recursive:
        for path in folder.rglob("*"):
            if skip_tree(path):
                continue
            if _hidden(path, folder) or not path.is_file() or path.is_symlink():
                continue
            if path.name in SKIP_NAMES or path.name.startswith("."):
                continue
            out.append(path)
        return out
    try:
        children = list(folder.iterdir())
    except OSError as exc:
        raise DeckProblem(f"Cannot read {folder} ({exc.strerror or exc})") from exc
    for path in children:
        if path.name.startswith(".") or path.name in SKIP_NAMES:
            continue
        if path.is_dir():
            if path.resolve() in skip:
                continue
            continue
        if path.is_file() and not path.is_symlink():
            out.append(path)
    return out


def match_globs(rel_posix: str, name: str, include: list[str], exclude: list[str]) -> bool:
    for pattern in exclude:
        if fnmatch.fnmatch(rel_posix, pattern) or fnmatch.fnmatch(name, pattern):
            return False
    if not include:
        return True
    for pattern in include:
        if fnmatch.fnmatch(rel_posix, pattern) or fnmatch.fnmatch(name, pattern):
            return True
    return False


def _under_sort_dir(path: Path, skip_dirs: set[Path]) -> bool:
    resolved = path.resolve()
    for directory in skip_dirs:
        try:
            resolved.relative_to(directory)
            return True
        except ValueError:
            continue
    return False


def _relative_posix(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


def _glob_list(raw) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw] if raw.strip() else []
    if isinstance(raw, list):
        return [str(x) for x in raw if str(x).strip()]
    return []


def _parse_sort_targets(raw: dict) -> dict[str, str]:
    targets: dict[str, str] = {}
    sort = raw.get("sort") or raw.get("sort_targets")
    if isinstance(sort, dict):
        for key, value in sort.items():
            if value:
                targets[str(key)] = str(value).strip("/\\")
    for key, value in raw.items():
        if key.startswith("sort_") and key != "sort_targets":
            direction = key[5:]
            if direction and value:
                targets[direction] = str(value).strip("/\\")
    return targets
