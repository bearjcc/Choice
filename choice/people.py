# SPDX-License-Identifier: AGPL-3.0-only
"""Optional people.

`.choice/users.json` next to the path you pointed Choice at.
No file means one shared log and every deck, as before.

A name picks a log. It is not a password: anyone who can open the
page can pick a name and change who sees which deck.
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass
from pathlib import Path

from choice.load import DeckProblem, slug

_WRITE = threading.Lock()
_ID_OK = re.compile(r"[a-z0-9_-]+")
_NAME_LIMIT = 48


@dataclass
class Person:
    id: str
    name: str
    # None means every deck, including ones added later.
    decks: list[str] | None

    def sees(self, deck_id: str) -> bool:
        if self.decks is None:
            return True
        return deck_id in self.decks

    def public(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "decks": "*" if self.decks is None else list(self.decks),
        }


@dataclass
class Roster:
    people: list[Person]
    warnings: list[str]
    # True when users.json exists. An empty list still counts: the shared
    # log stays unused until the file is removed.
    enabled: bool

    def get(self, person_id: str) -> Person | None:
        for person in self.people:
            if person.id == person_id:
                return person
        return None


def roster_path(root: Path) -> Path:
    root = root.expanduser().resolve()
    base = root.parent if root.is_file() else root
    return base / ".choice" / "users.json"


def load_roster(root: Path) -> Roster:
    path = roster_path(root)
    if not path.is_file():
        return Roster([], [], False)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DeckProblem(f"Cannot read users.json ({exc.strerror or exc})") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DeckProblem(f"users.json is not valid JSON ({exc.msg})") from exc
    if not isinstance(data, dict) or "users" not in data:
        raise DeckProblem("users.json needs a users list.")
    rows = data.get("users")
    if not isinstance(rows, list):
        raise DeckProblem("users.json: users must be a list.")
    warnings = []
    for key in data:
        if key != "users":
            warnings.append(f"users.json: unknown key '{key}' (ignored)")
    people: list[Person] = []
    seen: set[str] = set()
    for row in rows:
        try:
            person = _person(row, warnings, known=None)
        except DeckProblem as exc:
            warnings.append(str(exc))
            continue
        if person.id in seen:
            warnings.append(f"{person.name}: duplicate id '{person.id}' (ignored)")
            continue
        seen.add(person.id)
        people.append(person)
    return Roster(people, warnings, True)


def assignment_warnings(people: list[Person], deck_ids: set[str]) -> list[str]:
    notes = []
    for person in people:
        if person.decks is None:
            continue
        for deck_id in person.decks:
            if deck_id not in deck_ids:
                notes.append(f"{person.name}: no deck '{deck_id}'")
    return notes


def save_roster(root: Path, people: list[Person]) -> None:
    path = roster_path(root)
    payload = {"users": [person.public() for person in people]}
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    _write(path, text)


def drop_deck_from_roster(root: Path, deck_id: str) -> None:
    """Remove one deck id from every person's assignment list."""
    try:
        roster = load_roster(root)
    except DeckProblem:
        return
    if not roster.enabled:
        return
    changed = False
    people: list[Person] = []
    for person in roster.people:
        if person.decks is None:
            people.append(person)
            continue
        if deck_id not in person.decks:
            people.append(person)
            continue
        kept = [d for d in person.decks if d != deck_id]
        people.append(Person(person.id, person.name, kept))
        changed = True
    if changed:
        save_roster(root, people)


def remove_roster(root: Path) -> None:
    path = roster_path(root)
    with _WRITE:
        try:
            if path.is_file():
                path.unlink()
        except OSError as exc:
            raise DeckProblem(f"Cannot update users.json ({exc.strerror or exc})") from exc


def parse_users(raw: list, known: set[str]) -> list[Person]:
    """The list the page is saving. Unknown decks are refused."""
    if not isinstance(raw, list):
        raise DeckProblem("Send a users list.")
    people = []
    seen: set[str] = set()
    for row in raw:
        person = _person(row, warnings=None, known=known)
        if person.id in seen:
            raise DeckProblem(f"{person.name} is already here.")
        seen.add(person.id)
        people.append(person)
    return people


def _person(row, warnings: list[str] | None, known: set[str] | None) -> Person:
    strict = warnings is None
    if not isinstance(row, dict):
        raise DeckProblem("Each person must be an object.")
    if strict:
        for key in row:
            if key not in {"id", "name", "decks"}:
                raise DeckProblem(f"Unknown field '{key}'.")
    name = row.get("name")
    if not isinstance(name, str) or not name.strip():
        raise DeckProblem("Each person needs a name.")
    name = " ".join(name.split())
    if len(name) > _NAME_LIMIT:
        raise DeckProblem(f"Name is longer than {_NAME_LIMIT} characters.")
    if warnings is not None:
        for key in row:
            if key not in {"id", "name", "decks"}:
                warnings.append(f"{name}: unknown key '{key}' (ignored)")
    given = row.get("id")
    if given in (None, ""):
        person_id = slug(name)
        if not any(ch.isalnum() for ch in name):
            person_id = "person"
    else:
        if not isinstance(given, str) or not _ID_OK.fullmatch(given):
            raise DeckProblem(f"{name}: bad id.")
        person_id = given
    if "decks" not in row:
        decks = None
    else:
        decks = _decks(row.get("decks"), name, known, warnings)
    return Person(person_id, name, decks)


def _decks(raw, name: str, known: set[str] | None, warnings: list[str] | None) -> list[str] | None:
    if raw is None or raw == "*":
        return None
    if not isinstance(raw, list):
        raise DeckProblem(f"{name}: decks must be a list or '*'.")
    decks: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not _ID_OK.fullmatch(item):
            if warnings is None:
                raise DeckProblem(f"{name}: bad deck id.")
            warnings.append(f"{name}: ignored deck '{item}'")
            continue
        if known is not None and item not in known:
            raise DeckProblem(f"No such deck '{item}'.")
        if item not in decks:
            decks.append(item)
    return decks


def _write(path: Path, text: str) -> None:
    from choice.atomic_io import write_text_atomic

    with _WRITE:
        try:
            write_text_atomic(path, text)
        except OSError as exc:
            raise DeckProblem(f"Cannot update users.json ({exc.strerror or exc})") from exc
