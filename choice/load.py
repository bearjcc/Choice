# SPDX-License-Identifier: AGPL-3.0-only
"""Find a deck and turn its source into cards.

Discovery rules (the long version is DECKS.md):

1. A file named deck.json, or a .jsonl/.csv/.json file, is one deck.
2. A folder with deck.json is that deck.
3. A folder whose children have deck.json or items.jsonl/csv/json is a library.
4. A folder of files, pointed at directly, is one deck (images preview).
5. Dot-folders, including .choice, are never part of the pile.

Choice reads the whole source on each request so a new file shows up
without a restart. A deck is a review pile, not a database.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".avif"}
ITEM_FILES = ("items.jsonl", "items.csv", "items.json")
SKIP_NAMES = {"deck.json"}
_TEMPLATE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_DECK_KEYS = {"title", "blind", "source", "show", "directions", "buttons", "hook", "score", "contest", "story"}
_FIELD = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SOURCE_KEYS = {
    "type",
    "path",
    "id",
    "recursive",
    "output",
    "output_mode",
    "include",
    "exclude",
    "include_globs",
    "exclude_globs",
    "sort",
    "sort_targets",
}
_SHOW_KEYS = {"title", "body", "chips", "reveal", "image", "pair"}
_PAIR_SIDE_KEYS = {"body", "image", "label"}
_DIR_KEYS = {"label", "value", "later", "does", "into", "color"}
_HOOK_KEYS = {"command", "required", "timeout_seconds"}
_FOUR = ("left", "right", "up", "down")


class DeckProblem(Exception):
    """Something the reader can fix. The message is shown on the page."""


@dataclass
class Direction:
    id: str
    label: str
    value: str
    later: bool = False
    does: str = "label"
    into: str | None = None
    color: str | None = None

    def public(self) -> dict:
        out = {
            "id": self.id,
            "label": self.label,
            "value": self.value,
            "later": self.later,
            "does": self.does,
        }
        if self.color:
            out["color"] = self.color
        return out


@dataclass
class Side:
    """One half of an A/B card. `a` is the left swipe, `b` is the right."""

    key: str
    label: str
    body: str
    path: Path | None = None
    media_token: str = ""

    def public(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "body": self.body,
            "media": self.path is not None,
            "media_token": self.media_token,
        }


@dataclass
class Item:
    id: str
    kind: str
    title: str
    body: str
    chips: list[tuple[str, str]] = field(default_factory=list)
    reveal: list[tuple[str, str]] = field(default_factory=list)
    path: Path | None = None
    media_token: str = ""
    fields: dict = field(default_factory=dict)
    sides: list[Side] = field(default_factory=list)
    # offers: direction id -> button text. An empty string hides that swipe.
    # picks stay on the server. They are the value written for that swipe.
    offers: dict | None = None
    picks: dict | None = None
    pick_labels: dict | None = None

    def public(self, choice: str | None) -> dict:
        out = {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "body": self.body,
            "chips": [{"label": k, "text": v} for k, v in self.chips],
            "reveal": [{"label": k, "text": v} for k, v in self.reveal],
            "media": self.path is not None and self.kind == "image",
            "media_token": self.media_token,
            "file": self.path.name if self.path else None,
            "choice": choice,
        }
        if self.kind == "pair":
            out["sides"] = [side.public() for side in self.sides]
        if self.offers is not None:
            out["offers"] = self.offers
        return out


@dataclass
class Deck:
    id: str
    title: str
    root: Path
    state_dir: Path
    directions: dict[str, Direction]
    buttons: list[Direction]
    blind: bool
    warnings: list[str]
    problem: str | None = None
    # Filled by the loader. Not for the page.
    _load: object = None
    hook: list[str] | None = None
    hook_required: bool = False
    hook_timeout: float = 20
    score_field: str | None = None
    contest_kind: str | None = None
    contest_name: str = "name"
    story: dict | None = None
    # Swipe deck.py adapter or remote media hook (see choice.swipe_plugin).
    plugin: object | None = None
    folder_scan: object | None = None
    # Set per request. None is the shared log.
    actor: str | None = None

    def load_items(self) -> tuple[list[Item], list[str]]:
        if self.problem:
            raise DeckProblem(self.problem)
        items, warnings = self._load()
        return items, list(self.warnings) + list(warnings)

    def action(self, name: str) -> Direction | None:
        if name in self.directions:
            return self.directions[name]
        for button in self.buttons:
            if button.id == name:
                return button
        return None

    def public_meta(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "blind": self.blind,
            "warnings": self.warnings,
            "directions": [self.directions[k].public() for k in _FOUR if k in self.directions],
            "buttons": [b.public() for b in self.buttons],
        }


@dataclass
class Opened:
    """What `resolve` found at a path."""

    decks: list[Deck]
    direct: bool


def slug(name: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_-]+", "-", name).strip("-").lower()
    return text or "deck"


def inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def render(template: str, fields: dict) -> str:
    def sub(match: re.Match) -> str:
        value = fields.get(match.group(1), "")
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    return _TEMPLATE.sub(sub, template)


def resolve(path: Path) -> Opened:
    path = path.expanduser().resolve()
    if not path.exists():
        raise DeckProblem("No such path: %s" % path)
    if path.is_file():
        if path.name == "deck.json":
            return Opened([_from_folder(path.parent)], direct=True)
        if path.suffix.lower() in {".jsonl", ".csv", ".json"}:
            if (path.parent / "deck.json").is_file():
                return Opened([_from_folder(path.parent)], direct=True)
            return Opened([_implicit_records(path)], direct=True)
        raise DeckProblem("Point Choice at a folder, deck.json, or a .jsonl/.csv/.json file.")

    if (path / "deck.json").is_file():
        return Opened([_from_folder(path)], direct=True)

    children = _child_decks(path)
    if children:
        return Opened(children, direct=False)

    if (path / "items.jsonl").is_file() or (path / "items.csv").is_file() or (path / "items.json").is_file():
        return Opened([_from_folder(path)], direct=True)

    files = _list_files(path, recursive=False)
    if files:
        images_only = all(_is_image(p) for p in files)
        return Opened([_implicit_folder(path, images_only=images_only)], direct=True)

    raise DeckProblem(
        "Nothing to swipe in %s. Point Choice at a photo folder, a data file, "
        "or a deck. From this repo: python -m choice examples" % path
    )


def _child_decks(path: Path) -> list[Deck]:
    found = []
    try:
        names = sorted(path.iterdir(), key=lambda p: p.name.lower())
    except OSError as exc:
        raise DeckProblem("Cannot read %s (%s)" % (path, exc.strerror or exc)) from exc
    for child in names:
        if not child.is_dir() or child.is_symlink() or child.name.startswith("."):
            continue
        if (child / "deck.json").is_file() or any((child / name).is_file() for name in ITEM_FILES):
            try:
                found.append(_from_folder(child))
            except DeckProblem as exc:
                found.append(_broken(child, str(exc)))
    return _unique_ids(found)


def _broken(folder: Path, message: str) -> Deck:
    deck_id = slug(folder.name)
    return Deck(
        id=deck_id,
        title=folder.name,
        root=folder,
        state_dir=folder / ".choice",
        directions={},
        buttons=[],
        blind=False,
        warnings=[],
        problem=message,
        _load=lambda: ([], []),
    )


def _unique_ids(decks: list[Deck]) -> list[Deck]:
    seen: dict[str, int] = {}
    for deck in decks:
        n = seen.get(deck.id, 0) + 1
        seen[deck.id] = n
        if n > 1:
            deck.id = "%s-%d" % (deck.id, n)
    return decks


def _from_folder(folder: Path) -> Deck:
    config_path = folder / "deck.json"
    if config_path.is_file():
        return _from_config(folder, _read_json_object(config_path, "deck.json"))
    for name in ITEM_FILES:
        if (folder / name).is_file():
            data = {
                "title": folder.name,
                "source": {"type": _source_type_for(name), "path": name},
            }
            return _from_config(folder, data, warnings=[])
    raise DeckProblem("%s has no deck.json or items file." % folder.name)


def _source_type_for(name: str) -> str:
    if name.endswith(".csv"):
        return "csv"
    if name.endswith(".jsonl"):
        return "jsonl"
    return "json"


def _implicit_records(path: Path) -> Deck:
    kind = {".csv": "csv", ".jsonl": "jsonl"}.get(path.suffix.lower(), "json")
    data = {"title": path.stem, "source": {"type": kind, "path": path.name}}
    deck = _from_config(path.parent, data, warnings=[])
    deck.id = slug(path.name)
    deck.state_dir = path.parent / ".choice" / deck.id
    deck.title = path.stem
    return deck


def _implicit_folder(folder: Path, images_only: bool) -> Deck:
    from choice.folder_deck import default_results_directions

    data = {
        "title": folder.name,
        "source": {"type": "images" if images_only else "files", "path": ".", "output": "results"},
        "directions": {k: v for k, v in _file_directions().items()},
    }
    deck = _from_config(folder, data, warnings=[])
    deck.directions = default_results_directions()
    return deck


def _file_directions() -> dict:
    return {
        "right": {"label": "Keep", "value": "keep"},
        "left": {"label": "Trash", "value": "trash", "does": "move", "into": ".choice/trash"},
        "up": {"label": "Favourite", "value": "favourite"},
        "down": {"label": "Skip", "value": "skip", "later": True},
    }


def _read_json_object(path: Path, label: str) -> dict:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DeckProblem("Cannot read %s (%s)" % (label, exc.strerror or exc)) from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DeckProblem("%s is not valid JSON (%s)" % (label, exc.msg)) from exc
    if not isinstance(data, dict):
        raise DeckProblem("%s must be a JSON object." % label)
    return data


def _from_config(folder: Path, data: dict, warnings: list[str] | None = None) -> Deck:
    notes = list(warnings or [])
    for key in data:
        if key not in _DECK_KEYS:
            notes.append("deck.json: unknown key '%s' (ignored)" % key)

    title = data.get("title") or folder.name
    if not isinstance(title, str):
        raise DeckProblem("title must be a string.")

    source = data.get("source") or {}
    if not isinstance(source, dict):
        raise DeckProblem("source must be an object.")
    for key in source:
        if key not in _SOURCE_KEYS:
            notes.append("source: unknown key '%s' (ignored)" % key)

    show = data.get("show") or {}
    if not isinstance(show, dict):
        raise DeckProblem("show must be an object.")
    for key in show:
        if key not in _SHOW_KEYS:
            notes.append("show: unknown key '%s' (ignored)" % key)

    directions = _directions(data.get("directions"))
    buttons = _buttons(data.get("buttons"))
    if not directions and not buttons:
        directions = _yes_no()

    score_field, score_notes = _score(data.get("score"))
    contest_kind, contest_name, contest_notes = _contest(data.get("contest"))
    story, story_notes = _story(data.get("story"))
    notes.extend(score_notes)
    notes.extend(contest_notes)
    notes.extend(story_notes)
    _check_modes(directions, score_field, contest_kind, story)

    hook, hook_required, hook_timeout, hook_notes = _hook(data.get("hook"))
    notes.extend(hook_notes)

    deck_id = slug(folder.name)
    root = folder.resolve()

    labels = (
        directions["left"].label if "left" in directions else "A",
        directions["right"].label if "right" in directions else "B",
    )

    def load() -> tuple[list[Item], list[str]]:
        return _load_source(root, source, show, labels)

    deck = Deck(
        id=deck_id,
        title=title,
        root=root,
        state_dir=root / ".choice",
        directions=directions,
        buttons=buttons,
        blind=bool(data.get("blind")),
        warnings=notes,
        _load=load,
        hook=hook,
        hook_required=hook_required,
        hook_timeout=hook_timeout,
        score_field=score_field,
        contest_kind=contest_kind,
        contest_name=contest_name,
        story=story,
    )
    src_kind = str(source.get("type") or "files")
    if src_kind in {"images", "files"} and (
        source.get("output")
        or source.get("output_mode")
        or source.get("sort")
        or source.get("sort_targets")
        or source.get("include")
        or source.get("exclude")
    ):
        from choice.folder_deck import merge_folder_options, wire_sort_buttons, wire_sort_directions

        scan = merge_folder_options(source, {})
        deck.folder_scan = scan
        if scan.output == "sort":
            deck.directions = wire_sort_directions(deck.directions, scan.sort_targets)
            deck.buttons = wire_sort_buttons(deck.buttons, scan.sort_targets)
    return deck


def _score(raw) -> tuple[str | None, list[str]]:
    if raw is None:
        return None, []
    if not isinstance(raw, dict):
        raise DeckProblem("score must be an object.")
    notes = ["score: unknown key '%s' (ignored)" % key for key in raw if key != "field"]
    field_name = raw.get("field")
    if not isinstance(field_name, str) or not _FIELD.match(field_name):
        raise DeckProblem("score.field must be a field name.")
    return field_name, notes


def _contest(raw) -> tuple[str | None, str, list[str]]:
    if raw is None:
        return None, "name", []
    if not isinstance(raw, dict):
        raise DeckProblem("contest must be an object.")
    notes = ["contest: unknown key '%s' (ignored)" % key for key in raw if key not in {"kind", "name"}]
    kind = raw.get("kind")
    if kind not in {"robin", "bracket"}:
        raise DeckProblem("contest.kind must be robin or bracket.")
    name = raw.get("name") or "name"
    if not isinstance(name, str) or not _FIELD.match(name):
        raise DeckProblem("contest.name must be a field name.")
    return kind, name, notes


def _story(raw) -> tuple[dict | None, list[str]]:
    if raw is None:
        return None, []
    if not isinstance(raw, dict):
        raise DeckProblem("story must be an object.")
    allowed = {"start", "labels", *_FOUR}
    notes = ["story: unknown key '%s' (ignored)" % key for key in raw if key not in allowed]
    nxt = {}
    for key in _FOUR:
        if key not in raw:
            continue
        field_name = raw.get(key)
        if not isinstance(field_name, str) or not _FIELD.match(field_name):
            raise DeckProblem("story.%s must be a field name." % key)
        nxt[key] = field_name
    if not nxt:
        raise DeckProblem("story needs a left or a right field, naming the next scene.")
    labels_raw = raw.get("labels") or {}
    if not isinstance(labels_raw, dict):
        raise DeckProblem("story.labels must be an object.")
    labels = {}
    for key, field_name in labels_raw.items():
        if key not in nxt:
            notes.append("story.labels: '%s' has no next field (ignored)" % key)
            continue
        if not isinstance(field_name, str) or not _FIELD.match(field_name):
            raise DeckProblem("story.labels.%s must be a field name." % key)
        labels[key] = field_name
    start = raw.get("start") or ""
    if not isinstance(start, str):
        raise DeckProblem("story.start must be a card id.")
    return {"start": start, "next": nxt, "labels": labels}, notes


def _check_modes(directions, score_field, contest_kind, story) -> None:
    modes = [name for name, on in (("score", score_field), ("contest", contest_kind), ("story", story)) if on]
    if len(modes) > 1:
        raise DeckProblem("Use only one of score, contest, and story.")
    if contest_kind:
        left = directions.get("left")
        right = directions.get("right")
        if left is None or right is None:
            raise DeckProblem("contest needs a left and a right swipe.")
        if left.later or right.later:
            raise DeckProblem("contest: left and right pick a side, so they cannot be later.")
    if story:
        for key in story["next"]:
            if key not in directions:
                raise DeckProblem("story.%s needs a %s swipe." % (key, key))
        for key, direction in directions.items():
            if key not in story["next"] and not direction.later:
                raise DeckProblem(
                    "story: '%s' needs later: true, or a next field. Only a story swipe turns the page." % key
                )


def _yes_no() -> dict[str, Direction]:
    spec = {
        "right": {"label": "Yes", "value": "yes"},
        "left": {"label": "No", "value": "no"},
        "down": {"label": "Skip", "value": "skip", "later": True},
    }
    return _directions(spec)


def _directions(raw) -> dict[str, Direction]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise DeckProblem("directions must be an object.")
    out = {}
    for key, spec in raw.items():
        if key not in _FOUR:
            raise DeckProblem("direction '%s' is not left, right, up, or down." % key)
        out[key] = _one_direction(key, spec)
    return out


def _buttons(raw) -> list[Direction]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise DeckProblem("buttons must be a list.")
    out = []
    for spec in raw:
        if not isinstance(spec, dict) or not spec.get("id"):
            raise DeckProblem("each button needs an id.")
        name = str(spec["id"])
        if name in _FOUR or name in {"undo", "note"}:
            raise DeckProblem("button id '%s' is reserved." % name)
        out.append(_one_direction(name, spec))
    return out


def _one_direction(name: str, spec) -> Direction:
    if not isinstance(spec, dict):
        raise DeckProblem("direction %s must be an object." % name)
    label = spec.get("label") or name
    if not isinstance(label, str):
        raise DeckProblem("label on %s must be a string." % name)
    value = spec.get("value")
    if value is None:
        value = slug(label) or name
    value = str(value)
    does = spec.get("does") or "label"
    if does not in {"label", "move", "copy"}:
        raise DeckProblem("%s: does must be label, move, or copy." % name)
    into = spec.get("into")
    if into is not None:
        into = str(into).replace("\\", "/").strip("/")
        if not into or into.startswith("/") or ".." in into.split("/"):
            raise DeckProblem("%s: into must stay inside the deck folder." % name)
    if does in {"move", "copy"} and not into:
        into = ".choice/out/" + slug(value)
    color = spec.get("color")
    if color is not None and not (isinstance(color, str) and _HEX.match(color)):
        color = None
    return Direction(
        id=name,
        label=label,
        value=value,
        later=bool(spec.get("later")),
        does=does,
        into=into,
        color=color if isinstance(color, str) else None,
    )


def _hook(raw) -> tuple[list[str] | None, bool, float, list[str]]:
    if raw is None:
        return None, False, 20, []
    if not isinstance(raw, dict):
        raise DeckProblem("hook must be an object with a command list.")
    notes = ["hook: unknown key '%s' (ignored)" % k for k in raw if k not in _HOOK_KEYS]
    command = raw.get("command")
    if not isinstance(command, list) or not command or not all(isinstance(p, str) and p for p in command):
        raise DeckProblem("hook.command must be a list of strings, without a shell.")
    timeout = raw.get("timeout_seconds", 20)
    try:
        timeout = float(timeout)
    except (TypeError, ValueError) as exc:
        raise DeckProblem("hook.timeout_seconds must be a number.") from exc
    if timeout < 1 or timeout > 120:
        raise DeckProblem("hook.timeout_seconds must be between 1 and 120.")
    return list(command), bool(raw.get("required")), timeout, notes


def _load_source(root: Path, source: dict, show: dict, labels: tuple[str, str] = ("A", "B")) -> tuple[list[Item], list[str]]:
    from choice.folder_deck import items_from_folder_scan, merge_folder_options

    kind = source.get("type") or "files"
    rel = source.get("path") or "."
    target = _source_path(root, str(rel))
    if kind in {"images", "files"}:
        if not target.is_dir():
            raise DeckProblem("source path is not a folder: %s" % rel)
        scan = merge_folder_options({**source, "type": kind}, {})
        return items_from_folder_scan(root, target, scan), []
    if kind not in {"jsonl", "csv", "json"}:
        raise DeckProblem("source.type must be images, files, jsonl, csv, or json.")
    if not target.is_file():
        raise DeckProblem("source file is missing: %s" % rel)
    rows, warnings = _read_rows(target, kind)
    return _items_from_rows(root, rows, show, str(source.get("id") or "id"), warnings, labels)


def _source_path(root: Path, rel: str) -> Path:
    raw = Path(rel)
    if raw.is_absolute():
        return raw
    parts = Path(rel.replace("\\", "/")).parts
    if ".." in parts:
        raise DeckProblem("source path cannot contain ..")
    return root / rel


def _items_from_files(root: Path, folder: Path, images_only: bool, recursive: bool) -> tuple[list[Item], list[str]]:
    warnings = []
    files = _list_files(folder, recursive=recursive)
    items = []
    for path in files:
        if images_only and not _is_image(path):
            continue
        if path.is_symlink():
            warnings.append("skipped symlink %s" % path.name)
            continue
        rel = _item_id(root, folder, path)
        kind = "image" if _is_image(path) else "file"
        title = path.name
        body = ""
        if kind == "file":
            body = _size_text(path)
        if path.suffix.lower() == ".heic":
            kind = "file"
            body = "HEIC photo. Choice will not preview it. A decision still applies to the file."
        items.append(Item(
            id=rel,
            kind=kind,
            title=title,
            body=body,
            path=path.resolve(),
            media_token=str(_mtime(path)),
            fields={"file": rel},
        ))
    items.sort(key=lambda item: item.id.lower())
    return items, warnings


def _item_id(root: Path, folder: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().relative_to(folder.resolve()).as_posix()


def _list_files(folder: Path, recursive: bool) -> list[Path]:
    out = []
    if recursive:
        for path in folder.rglob("*"):
            if _hidden(path, folder) or not path.is_file() or path.is_symlink():
                continue
            if path.name in SKIP_NAMES or path.name.startswith("."):
                continue
            out.append(path)
        return out
    try:
        children = list(folder.iterdir())
    except OSError as exc:
        raise DeckProblem("Cannot read %s (%s)" % (folder, exc.strerror or exc)) from exc
    for path in children:
        if path.name.startswith(".") or path.name in SKIP_NAMES:
            continue
        if path.is_file() and not path.is_symlink():
            out.append(path)
    return out


def _hidden(path: Path, folder: Path) -> bool:
    try:
        rel = path.relative_to(folder)
    except ValueError:
        return True
    return any(part.startswith(".") for part in rel.parts)


def _is_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXT


def _mtime(path: Path) -> int:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0


def _size_text(path: Path) -> str:
    try:
        size = path.stat().st_size
    except OSError:
        return "unreadable"
    if size < 1024:
        return "%d bytes" % size
    if size < 1024 * 1024:
        return "%d KB" % (size // 1024)
    return "%.1f MB" % (size / (1024 * 1024))


def _read_rows(path: Path, kind: str) -> tuple[list[dict], list[str]]:
    if kind == "csv":
        return _read_csv(path)
    if kind == "jsonl":
        return _read_jsonl(path)
    return _read_json_rows(path)


def _read_jsonl(path: Path) -> tuple[list[dict], list[str]]:
    rows, warnings = [], []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise DeckProblem("Cannot read %s (%s)" % (path.name, exc.strerror or exc)) from exc
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            warnings.append("%s:%d is not valid JSON (skipped)" % (path.name, number))
            continue
        if not isinstance(row, dict):
            warnings.append("%s:%d is not an object (skipped)" % (path.name, number))
            continue
        rows.append(row)
    return rows, warnings


def _read_csv(path: Path) -> tuple[list[dict], list[str]]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise DeckProblem("Cannot read %s (%s)" % (path.name, exc.strerror or exc)) from exc
    reader = csv.DictReader(text.splitlines())
    if not reader.fieldnames:
        raise DeckProblem("%s has no header row." % path.name)
    rows = []
    for row in reader:
        rows.append({k: v for k, v in row.items() if k is not None})
    return rows, []


def _read_json_rows(path: Path) -> tuple[list[dict], list[str]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise DeckProblem("Cannot read %s (%s)" % (path.name, exc.strerror or exc)) from exc
    except json.JSONDecodeError as exc:
        raise DeckProblem("%s is not valid JSON (%s)" % (path.name, exc.msg)) from exc
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        data = data["items"]
    if not isinstance(data, list):
        raise DeckProblem("%s must be a list of objects, or {\"items\": [...]}." % path.name)
    rows, warnings = [], []
    for number, row in enumerate(data, start=1):
        if isinstance(row, dict):
            rows.append(row)
        else:
            warnings.append("%s item %d is not an object (skipped)" % (path.name, number))
    return rows, warnings


def _items_from_rows(
    root: Path,
    rows: list[dict],
    show: dict,
    id_field: str,
    warnings: list[str],
    labels: tuple[str, str] = ("A", "B"),
) -> tuple[list[Item], list[str]]:
    items = []
    seen = set()
    image_field = show.get("image")
    chips_set = "chips" in show
    chips = show.get("chips") if chips_set else []
    reveal = show.get("reveal") or []
    if not isinstance(chips, list) or not isinstance(reveal, list):
        raise DeckProblem("show.chips and show.reveal must be lists of field names.")
    pair, pair_notes, pair_hidden = _pair_spec(show)
    warnings.extend(pair_notes)
    if pair and image_field:
        warnings.append("show.image is ignored on a pair card")
    for index, row in enumerate(rows, start=1):
        item_id = row.get(id_field)
        if item_id is None or item_id == "":
            item_id = str(index)
        item_id = str(item_id)
        if item_id in seen:
            warnings.append("duplicate id '%s' (skipped the later row)" % item_id)
            continue
        seen.add(item_id)
        title = _show_text(show.get("title"), row, _guess_title(row, item_id))
        body = _show_text(show.get("body"), row, _guess_body(row))
        sides: list[Side] = []
        path = None
        kind = "text"
        if pair:
            kind = "pair"
            sides, side_notes = _pair_sides(root, row, pair, labels)
            warnings.extend(side_notes)
        else:
            path, kind, image_warning = _row_image(root, row, image_field)
            if image_warning:
                warnings.append(image_warning)
        chip_hidden = pair_hidden if pair else ()
        items.append(Item(
            id=item_id,
            kind=kind,
            title=title,
            body=body,
            chips=_pairs(row, chips) if chips_set else _guess_chips(row, id_field, image_field, reveal, chip_hidden),
            reveal=_pairs(row, reveal),
            path=path,
            media_token=str(_mtime(path)) if path else "",
            fields=_flat(row),
            sides=sides,
        ))
    return items, warnings


def _pair_spec(show: dict) -> tuple[dict | None, list[str], set[str]]:
    raw = show.get("pair")
    if raw is None:
        return None, [], set()
    if not isinstance(raw, dict):
        raise DeckProblem("show.pair must be an object with a and b.")
    notes = ["show.pair: unknown key '%s' (ignored)" % key for key in raw if key not in {"a", "b"}]
    if "a" not in raw or "b" not in raw:
        raise DeckProblem("show.pair needs a and b.")
    spec = {}
    hidden: set[str] = set()
    for key in ("a", "b"):
        spec[key] = _pair_side_spec(key, raw[key], notes)
        body = spec[key]["body"]
        if isinstance(body, str):
            hidden.update(_TEMPLATE.findall(body))
        image = spec[key]["image"]
        if image:
            hidden.add(image)
    title = show.get("title")
    if isinstance(title, str):
        hidden.update(_TEMPLATE.findall(title))
    return spec, notes, hidden


def _pair_side_spec(key: str, raw, notes: list[str]) -> dict:
    if isinstance(raw, str):
        return {"body": raw, "image": None, "label": ""}
    if not isinstance(raw, dict):
        raise DeckProblem("show.pair.%s must be a string or an object." % key)
    notes.extend(
        "show.pair.%s: unknown key '%s' (ignored)" % (key, name)
        for name in raw
        if name not in _PAIR_SIDE_KEYS
    )
    body = raw.get("body")
    if body is not None and not isinstance(body, str):
        raise DeckProblem("show.pair.%s body must be a string." % key)
    image = raw.get("image")
    if image is not None and (not isinstance(image, str) or not image.strip()):
        raise DeckProblem("show.pair.%s image must be a field name." % key)
    label = raw.get("label") or ""
    if not isinstance(label, str):
        raise DeckProblem("show.pair.%s label must be a string." % key)
    if body is None and not image:
        raise DeckProblem("show.pair.%s needs a body or an image." % key)
    return {"body": body, "image": image.strip() if isinstance(image, str) else None, "label": label}


def _pair_sides(root: Path, row: dict, spec: dict, labels: tuple[str, str]) -> tuple[list[Side], list[str]]:
    sides = []
    notes = []
    for key, fallback in (("a", labels[0]), ("b", labels[1])):
        side = spec[key]
        body = render(side["body"], row) if side["body"] else ""
        path = None
        if side["image"]:
            path, warning = _side_image(root, row, side["image"])
            if warning:
                notes.append("pair %s: %s" % (key, warning))
        sides.append(Side(
            key=key,
            label=side["label"] or fallback,
            body=body,
            path=path,
            media_token=str(_mtime(path)) if path else "",
        ))
    return sides, notes


def _side_image(root: Path, row: dict, field: str) -> tuple[Path | None, str | None]:
    raw = row.get(field)
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if not isinstance(raw, str) or not raw.strip():
        return None, "image field '%s' is empty" % field
    path = _source_path(root, raw.strip())
    if path.is_symlink():
        return None, "skipped symlink image %s" % raw
    if not path.is_file():
        return None, "image missing: %s" % raw
    if not _is_image(path):
        return None, "not an image: %s" % raw
    return path.resolve(), None


def _show_text(template, row: dict, fallback: str) -> str:
    if template is None:
        return fallback
    if not isinstance(template, str):
        raise DeckProblem("show title and body must be strings.")
    return render(template, row)


def _guess_title(row: dict, item_id: str) -> str:
    for key in ("title", "name", "question", "q", "prompt"):
        if row.get(key):
            return str(row[key])
    return item_id


def _guess_body(row: dict) -> str:
    for key in ("body", "text", "content", "detail", "prompt"):
        value = row.get(key)
        if isinstance(value, str) and value and key != "prompt":
            return value
    return ""


def _guess_chips(row: dict, id_field: str, image_field, reveal, extra=()) -> list[tuple[str, str]]:
    hidden = {id_field, "title", "name", "question", "q", "body", "text", "content", "detail", "image", "image_path", "images"}
    if image_field:
        hidden.add(str(image_field))
    hidden.update(str(name) for name in (reveal or []))
    hidden.update(str(name) for name in extra)
    pairs = []
    for key, value in row.items():
        if key in hidden or isinstance(value, (dict, list)) or value is None or value == "":
            continue
        pairs.append((str(key), str(value)))
        if len(pairs) == 6:
            break
    return pairs


def _pairs(row: dict, names) -> list[tuple[str, str]]:
    out = []
    for name in names:
        value = row.get(str(name))
        if value is None or value == "":
            continue
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        out.append((str(name), str(value)))
    return out


def _flat(row: dict) -> dict:
    out = {}
    for key, value in row.items():
        if isinstance(value, (dict, list)):
            continue
        out[str(key)] = "" if value is None else str(value)
    return out


def _row_image(root: Path, row: dict, image_field) -> tuple[Path | None, str, str | None]:
    raw = None
    if image_field:
        raw = row.get(str(image_field))
    if raw is None:
        raw = row.get("image", row.get("image_path"))
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if not isinstance(raw, str) or not raw.strip():
        return None, "text", None
    path = _source_path(root, raw.strip())
    if path.is_symlink():
        return None, "text", "skipped symlink image %s" % raw
    if not path.is_file():
        return None, "text", "image missing: %s" % raw
    if not _is_image(path):
        return None, "text", None
    return path.resolve(), "image", None
