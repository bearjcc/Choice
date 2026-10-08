# SPDX-License-Identifier: AGPL-3.0-only
"""Apply a swipe and undo it.

The log at `.choice/decisions.jsonl` is the source of truth. The latest
record for an item wins. An undo is another line; it does not rewrite history.

`does: move` renames a file. It never deletes one. Undo moves it back.
A file outside the deck folder can be labelled and cannot be moved.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
import uuid
from datetime import datetime
from pathlib import Path

from choice.flow import Flow, arrange, report_lines
from choice.load import Deck, DeckProblem, Item, inside

_GUARD = threading.Lock()
_LOCKS: dict[str, threading.Lock] = {}


def decide(deck: Deck, item_id: str, direction: str, note: str | None) -> dict:
    action = deck.action(direction)
    if action is None:
        return _fail("Unknown action '%s'." % direction)
    note = (note or "").strip()
    if len(note) > 500:
        return _fail("Note is longer than 500 characters.")

    with _lock(deck):
        try:
            flow = view(deck)
        except DeckProblem as exc:
            return _fail(str(exc))
        item = _find(flow.items, item_id)
        if item is None:
            return _fail("That card is not in the pile.")
        token = uuid.uuid4().hex
        record = {
            "type": "decision",
            "id": token,
            "item": item.id,
            "direction": action.id,
            "value": action.value,
            "label": action.label,
            "later": action.later,
            "note": note,
            "ts": _now(),
            "file": item.path.name if item.path else None,
        }
        _apply_pick(deck, item, action, record)
        moved = None
        try:
            if action.does in {"move", "copy"}:
                moved = _transfer(deck, item, action.does, action.into or "")
                record["file_op"] = moved
            if deck.hook and deck.hook_required:
                _run_hook(deck, _hook_body("decide", deck, item, record))
        except _OpError as exc:
            if moved is not None:
                try:
                    _reverse_file_op(deck, moved)
                except _OpError:
                    return _fail("%s Choice could not reverse the file change." % exc)
            return _fail(str(exc))

        _append(deck, record)
        message = "%s: %s" % (record["label"], item.title)
        if deck.hook and not deck.hook_required:
            try:
                _run_hook(deck, _hook_body("decide", deck, item, record))
            except _OpError as exc:
                message += " Saved here, but the hook failed: %s" % exc
        return {"ok": True, "message": message, "can_undo": True}


def undo(deck: Deck) -> dict:
    with _lock(deck):
        latest = _latest_undoable(deck)
        if latest is None:
            return _fail("Nothing to undo.")
        item = Item(
            id=latest["item"],
            kind="file",
            title=latest.get("file") or latest["item"],
            body="",
            path=None,
            fields={"item": latest["item"]},
        )
        reversed_op = False
        try:
            if latest.get("file_op"):
                _reverse_file_op(deck, latest.get("file_op"))
                reversed_op = True
            if deck.hook and deck.hook_required:
                _run_hook(deck, _hook_body("undo", deck, item, latest))
        except _OpError as exc:
            if reversed_op:
                try:
                    _reapply_file_op(deck, latest.get("file_op"))
                except _OpError:
                    return _fail("%s Choice could not put the file back." % exc)
            return _fail(str(exc))
        _append(deck, {"type": "undo", "ref": latest["id"], "item": latest["item"], "ts": _now()})
        if deck.hook and not deck.hook_required:
            try:
                _run_hook(deck, _hook_body("undo", deck, item, latest))
            except _OpError as exc:
                return {
                    "ok": True,
                    "message": "Undone here, but the hook failed: %s" % exc,
                    "can_undo": _latest_undoable(deck) is not None,
                }
        undone = latest.get("file") or latest.get("label") or item.title
        return {"ok": True, "message": "Undone %s" % undone, "can_undo": _latest_undoable(deck) is not None}


def view(deck: Deck, items: list[Item] | None = None) -> Flow:
    """The cards to show, built from the rows and the log."""
    loaded: list[str] = []
    if items is None:
        items, loaded = deck.load_items()
    choices = _choices(deck)
    flow = arrange(deck, items, choices)
    flow.warnings = list(loaded) + list(flow.warnings)
    flow.choices = choices
    return flow


def progress(deck: Deck, pending: bool, items: list[Item] | None = None) -> dict:
    """Counts, tally, and the cards still to show. Caller may pass items it already loaded."""
    try:
        flow = view(deck, items)
    except DeckProblem as exc:
        return {"ok": False, "message": str(exc), "warnings": []}
    choices = flow.choices
    visible = []
    decided = 0
    for item in flow.items:
        choice = choices.get(item.id)
        current = choice.get("value") if choice else None
        if choice is not None and not choice.get("later"):
            decided += 1
            if pending:
                continue
        shown = item.public(current)
        if choice and choice.get("label"):
            shown["choice_label"] = choice.get("label")
        mark = flow.marks.get(item.id)
        if mark:
            shown["mark"] = mark.get("mark")
            if mark.get("note"):
                shown["mark_note"] = mark.get("note")
        visible.append(shown)
    tally = _tally(deck, choices)
    total = len(flow.items)
    left = total - decided
    if flow.total is not None:
        total = flow.total
        decided = flow.decided if flow.decided is not None else decided
        left = flow.left if flow.left is not None else total - decided
    out = {
        "ok": True,
        "total": total,
        "decided": decided,
        "left": left,
        "can_undo": _has_undo(deck),
        "tally": tally,
        "items": visible,
        "warnings": flow.warnings,
        "pending": pending,
    }
    if flow.report:
        out["report"] = flow.report
    if flow.count_label:
        out["count_label"] = flow.count_label
    if flow.meter is not None:
        out["meter"] = flow.meter
    if flow.replay is not None:
        out["replay"] = flow.replay
    return out


def tally_lines(deck: Deck) -> list[str]:
    try:
        flow = view(deck)
    except DeckProblem as exc:
        return [str(exc)]
    choices = flow.choices
    counts: dict[str, int] = {}
    labels: dict[str, str] = {}
    for record in choices.values():
        if record.get("later"):
            key = record.get("value") or "later"
            counts[key] = counts.get(key, 0) + 1
            labels[key] = record.get("label") or key
            continue
        key = record.get("value") or "?"
        counts[key] = counts.get(key, 0) + 1
        labels[key] = record.get("label") or key
    total = flow.total if flow.total is not None else len(flow.items)
    decided = flow.decided if flow.decided is not None else sum(
        1 for record in choices.values() if not record.get("later")
    )
    left = flow.left if flow.left is not None else total - decided
    lines = report_lines(flow.report)
    if lines:
        lines.append("")
    lines.append("%d cards, %d decided, %d left" % (total, decided, left))
    for key, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append("%s: %d" % (labels.get(key, key), count))
    if len(lines) == 1:
        lines.append("No decisions yet.")
    return lines


def _tally(deck: Deck, choices: dict[str, dict]) -> list[dict]:
    labels = {}
    for direction in list(deck.directions.values()) + deck.buttons:
        labels[direction.value] = direction.label
    counts: dict[str, int] = {}
    for record in choices.values():
        key = record.get("value") or "?"
        counts[key] = counts.get(key, 0) + 1
        labels.setdefault(key, record.get("label") or key)
    return [{"value": key, "label": labels.get(key, key), "n": counts[key]} for key in sorted(counts)]


def _choices(deck: Deck) -> dict[str, dict]:
    """Latest decision per item that has not been undone.

    Undo marks one decision id as dead. An earlier decision for that card
    counts again. The log itself is never rewritten.
    """
    records = _read_log(deck)
    dead = {record.get("ref") for record in records if record.get("type") == "undo"}
    latest: dict[str, dict] = {}
    for record in records:
        if record.get("type") != "decision" or record.get("id") in dead:
            continue
        item = record.get("item")
        if item:
            latest[str(item)] = record
    return latest


def _has_undo(deck: Deck) -> bool:
    return _latest_undoable(deck) is not None


def _latest_undoable(deck: Deck) -> dict | None:
    records = _read_log(deck)
    dead = {record.get("ref") for record in records if record.get("type") == "undo"}
    last = None
    for record in records:
        if record.get("type") == "decision" and record.get("id") not in dead:
            last = record
    return last


def _transfer(deck: Deck, item: Item, does: str, into: str) -> dict:
    if item.path is None:
        raise _OpError("This card has no file to %s." % does)
    if not item.path.is_file():
        raise _OpError("File is already gone: %s" % item.title)
    if not inside(deck.root, item.path):
        raise _OpError("Choice will not %s a file outside the deck folder." % does)
    dest_root = (deck.root / into).resolve()
    if not inside(deck.root, dest_root):
        raise _OpError("into leaves the deck folder.")
    try:
        rel = item.path.resolve().relative_to(deck.root.resolve())
    except ValueError as exc:
        raise _OpError("Choice will not %s a file outside the deck folder." % does) from exc
    dest = dest_root / rel
    dest = dest.resolve()
    if not inside(deck.root, dest):
        raise _OpError("That destination leaves the deck folder.")
    if dest.exists():
        raise _OpError("Already a file at %s" % dest.relative_to(deck.root.resolve()).as_posix())
    dest.parent.mkdir(parents=True, exist_ok=True)
    if does == "move":
        shutil.move(str(item.path), str(dest))
    else:
        shutil.copy2(item.path, dest)
    return {
        "op": does,
        "from": rel.as_posix(),
        "to": dest.relative_to(deck.root.resolve()).as_posix(),
    }


def _reapply_file_op(deck: Deck, file_op: dict | None) -> None:
    """Put a file back the way a failed undo found it."""
    if not file_op:
        return
    src = _under(deck.root, str(file_op.get("from") or ""))
    dest = _under(deck.root, str(file_op.get("to") or ""))
    dest.parent.mkdir(parents=True, exist_ok=True)
    if file_op.get("op") == "move":
        if not src.is_file():
            raise _OpError("the original file is missing")
        shutil.move(str(src), str(dest))
        return
    if file_op.get("op") == "copy":
        if not src.is_file():
            raise _OpError("the original file is missing")
        shutil.copy2(src, dest)


def _reverse_file_op(deck: Deck, file_op: dict | None) -> None:
    if not file_op:
        return
    op = file_op.get("op")
    src = _under(deck.root, str(file_op.get("from") or ""))
    dest = _under(deck.root, str(file_op.get("to") or ""))
    if op == "copy":
        if dest.is_file():
            dest.unlink()
        return
    if op != "move":
        return
    if not dest.is_file():
        raise _OpError("Cannot undo: %s is not there any more." % file_op.get("to"))
    if src.exists():
        raise _OpError("Cannot undo: %s is already back." % file_op.get("from"))
    src.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(dest), str(src))


def _under(root: Path, relative: str) -> Path:
    parts = Path(relative.replace("\\", "/")).parts
    if not relative or relative.startswith("/") or ".." in parts or Path(relative).is_absolute():
        raise _OpError("The decision log has a bad path, so undo stopped.")
    path = (root / relative).resolve()
    if not inside(root, path):
        raise _OpError("The decision log points outside the deck, so undo stopped.")
    return path


def _run_hook(deck: Deck, body: dict) -> None:
    try:
        result = subprocess.run(
            deck.hook,
            input=json.dumps(body).encode("utf-8"),
            cwd=str(deck.root),
            capture_output=True,
            timeout=deck.hook_timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise _OpError("hook timed out after %s seconds" % deck.hook_timeout) from exc
    except OSError as exc:
        raise _OpError("hook could not start (%s)" % (exc.strerror or exc)) from exc
    if result.returncode != 0:
        err = (result.stderr or result.stdout or b"").decode("utf-8", "replace").strip()
        err = err[-400:] if err else "exit %s" % result.returncode
        raise _OpError(err)


def _hook_body(action: str, deck: Deck, item: Item, record: dict) -> dict:
    return {
        "action": action,
        "deck": deck.id,
        "item": item.id,
        "direction": record.get("direction"),
        "value": record.get("value"),
        "label": record.get("label"),
        "note": record.get("note") or "",
        "file": record.get("file"),
        "fields": item.fields,
        "decision_id": record.get("id"),
        "user": deck.actor or "",
    }


def _append(deck: Deck, record: dict) -> None:
    path = _log_path(deck)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _read_log(deck: Deck) -> list[dict]:
    path = _log_path(deck)
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _log_path(deck: Deck) -> Path:
    if deck.actor:
        return deck.state_dir / "users" / deck.actor / "decisions.jsonl"
    return deck.state_dir / "decisions.jsonl"


def _apply_pick(deck: Deck, item: Item, action, record: dict) -> None:
    """A match records the chosen id. A story records the words on the button."""
    if action.later or not item.picks or action.id not in item.picks:
        return
    label = (item.pick_labels or {}).get(action.id) or action.label
    record["label"] = label
    if deck.story:
        record["value"] = label
        return
    record["value"] = item.picks[action.id]


def _find(items: list[Item], item_id: str) -> Item | None:
    for item in items:
        if item.id == item_id:
            return item
    return None


def _lock(deck: Deck) -> threading.Lock:
    key = str(deck.state_dir)
    with _GUARD:
        if key not in _LOCKS:
            _LOCKS[key] = threading.Lock()
        return _LOCKS[key]


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _fail(message: str) -> dict:
    return {"ok": False, "message": message}


class _OpError(Exception):
    pass
