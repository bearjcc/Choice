# SPDX-License-Identifier: AGPL-3.0-only
"""Apply a swipe and undo it.

The log at `.choice/decisions.jsonl` is the source of truth. The latest
record for an item wins. An undo is another line; it does not rewrite history.

`does: move` renames a file. It never deletes one. Undo moves it back.
A file outside the deck folder can be labelled and cannot be moved.
"""

from __future__ import annotations

import html
import json
import os
import shutil
import subprocess
import threading
import uuid
from datetime import datetime
from pathlib import Path

from choice.deck_cache import bust as bust_item_cache
from choice.deck_cache import load_items as cached_load_items
from choice.deck_index import (
    plugin_pile_counts,
    persisted_summary,
    refresh_persisted_summary,
    schedule_plugin_warm,
    snapshot,
)
from choice.flow import Flow, arrange, report_lines
from choice.load import Deck, DeckProblem, Item, inside

_GUARD = threading.Lock()
_LOCKS: dict[str, threading.Lock] = {}


def decide(deck: Deck, item_id: str, direction: str, note: str | None) -> dict:
    action = deck.action(direction)
    if action is None:
        return _fail(f"Unknown action '{direction}'.")
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
        if _plugin_done(item):
            return _fail("That card was already decided elsewhere.")
        prior = _choices(deck).get(item.id)
        if prior is not None:
            if (
                prior.get("direction") == action.id
                and (prior.get("note") or "") == note
                and not prior.get("later")
            ):
                return {
                    "ok": True,
                    "message": "{}: {} (already recorded)".format(
                        prior.get("label") or action.label, item.title
                    ),
                    "can_undo": _has_undo(deck),
                }
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
            if deck.plugin is not None:
                try:
                    plugin_result = _plugin_handle(deck, item, action.id, note)
                except Exception as exc:
                    return _fail(_plugin_error_text(exc))
                if not plugin_result.get("ok", True):
                    msg = _plugin_message(plugin_result.get("message"))
                    msg = msg or "Plugin refused the swipe."
                    return _fail(msg)
                if plugin_result.get("undo_token") is not None:
                    record["undo_token"] = plugin_result.get("undo_token")
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
                    return _fail(f"{exc} Choice could not reverse the file change.")
            return _fail(str(exc))

        _append(deck, record)
        bust_item_cache(deck)
        message = "{}: {}".format(record["label"], item.title)
        if deck.hook and not deck.hook_required:
            try:
                _run_hook(deck, _hook_body("decide", deck, item, record))
            except _OpError as exc:
                message += f" Saved here, but the hook failed: {exc}"
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
            if deck.plugin is not None and latest.get("undo_token") is not None:
                result = _plugin_undo(deck, latest["item"], latest.get("undo_token"))
                if not result.get("ok", True):
                    return _fail(result.get("message") or "Plugin could not undo.")
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
                    return _fail(f"{exc} Choice could not put the file back.")
            return _fail(str(exc))
        _append(deck, {"type": "undo", "ref": latest["id"], "item": latest["item"], "ts": _now()})
        bust_item_cache(deck)
        if deck.hook and not deck.hook_required:
            try:
                _run_hook(deck, _hook_body("undo", deck, item, latest))
            except _OpError as exc:
                return {
                    "ok": True,
                    "message": f"Undone here, but the hook failed: {exc}",
                    "can_undo": _latest_undoable(deck) is not None,
                }
        undone = latest.get("file") or latest.get("label") or item.title
        return {
            "ok": True,
            "message": f"Undone {undone}",
            "can_undo": _latest_undoable(deck) is not None,
        }


def view(deck: Deck, items: list[Item] | None = None) -> Flow:
    """The cards to show, built from the rows and the log."""
    loaded: list[str] = []
    if items is None:
        items, loaded = cached_load_items(deck)
    choices = _choices(deck)
    flow = arrange(deck, items, choices)
    flow.warnings = list(loaded) + list(flow.warnings)
    flow.choices = choices
    return flow


def index_summary(deck: Deck) -> dict:
    """Deck-list counts without calling list_items when a snapshot exists."""
    if deck.problem:
        return {
            "ok": False,
            "message": deck.problem,
            "total": 0,
            "decided": 0,
            "left": 0,
        }
    choices = _choices(deck)
    snap = snapshot(deck)
    log_decided = {item_id for item_id, row in choices.items() if not row.get("later")}
    if snap is None:
        if deck.plugin is None:
            snap_full = progress(deck, pending=True)
            if not snap_full.get("ok"):
                return {
                    "ok": False,
                    "message": snap_full.get("message"),
                    "total": 0,
                    "decided": 0,
                    "left": 0,
                }
            return {
                "ok": True,
                "total": snap_full["total"],
                "decided": snap_full["decided"],
                "left": snap_full["left"],
                "meter": snap_full.get("meter", True),
                "count_label": snap_full.get("count_label"),
            }
        schedule_plugin_warm(deck)
        saved = refresh_persisted_summary(deck)
        if saved is not None and saved.ids:
            total, decided, left, list_size = plugin_pile_counts(
                log_decided, saved.ids, saved.plugin_decided
            )
            return {
                "ok": True,
                "total": total,
                "decided": decided,
                "left": left,
                "list_size": list_size,
                "meter": True,
            }
        decided = len(log_decided)
        return {
            "ok": True,
            "total": None,
            "decided": decided,
            "left": None,
            "meter": False,
            "count_label": f"{decided} decided" if decided else None,
        }
    total, decided, left, list_size = plugin_pile_counts(
        log_decided, snap.ids, snap.plugin_decided
    )
    return {
        "ok": True,
        "total": total,
        "decided": decided,
        "left": left,
        "list_size": list_size,
        "meter": True,
    }


def run_plugin_action(deck: Deck, action_id: str) -> dict:
    plugin = deck.plugin
    if plugin is None:
        return _fail("This deck has no plugin actions.")
    run = getattr(plugin, "run_action", None)
    if not callable(run):
        return _fail("This deck has no plugin actions.")
    with _lock(deck):
        try:
            result = dict(run(action_id) or {})
        except Exception as exc:
            return _fail(_plugin_error_text(exc))
        if not result.get("ok", True):
            return _fail(_plugin_message(result.get("message")) or "Action failed.")
        bust_item_cache(deck)
        message = _plugin_message(result.get("message")) or "Done."
        return {"ok": True, "message": message}


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
        done_elsewhere = _plugin_done(item)
        log_done = choice is not None and not choice.get("later")
        if done_elsewhere or log_done:
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
    decided = (
        flow.decided
        if flow.decided is not None
        else sum(1 for record in choices.values() if not record.get("later"))
    )
    left = flow.left if flow.left is not None else total - decided
    lines = report_lines(flow.report)
    if lines:
        lines.append("")
    lines.append(f"{total} cards, {decided} decided, {left} left")
    for key, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"{labels.get(key, key)}: {count}")
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
    return [
        {"value": key, "label": labels.get(key, key), "n": counts[key]} for key in sorted(counts)
    ]


def _choices(deck: Deck) -> dict[str, dict]:
    """Latest decision per item that has not been undone."""
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
        raise _OpError(f"This card has no file to {does}.")
    if not item.path.is_file():
        raise _OpError(f"File is already gone: {item.title}")
    if not inside(deck.root, item.path):
        raise _OpError(f"Choice will not {does} a file outside the deck folder.")
    dest_root = (deck.root / into).resolve()
    if not inside(deck.root, dest_root):
        raise _OpError("into leaves the deck folder.")
    try:
        rel = item.path.resolve().relative_to(deck.root.resolve())
    except ValueError as exc:
        raise _OpError(f"Choice will not {does} a file outside the deck folder.") from exc
    into_norm = into.replace("\\", "/")
    if "/" in into_norm or into_norm.startswith("."):
        dest = (dest_root / rel).resolve()
    else:
        dest = (dest_root / rel.name).resolve()
    if not inside(deck.root, dest):
        raise _OpError("That destination leaves the deck folder.")
    dest = _unique_dest(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    src = item.path.resolve()
    if does == "move":
        _safe_move(src, dest)
    else:
        _safe_copy(src, dest)
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
        raise _OpError("Cannot undo: {} is not there any more.".format(file_op.get("to")))
    if src.exists():
        raise _OpError("Cannot undo: {} is already back.".format(file_op.get("from")))
    src.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(dest), str(src))


def _unique_dest(dest: Path) -> Path:
    if not dest.exists():
        return dest
    stem, suffix = dest.stem, dest.suffix
    parent = dest.parent
    n = 1
    while n < 10000:
        candidate = parent / f"{stem}_{n}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1
    raise _OpError(f"Could not find a free name near {dest.name}.")


def _same_volume(a: Path, b: Path) -> bool:
    try:
        return os.stat(a).st_dev == os.stat(b.parent).st_dev
    except OSError:
        return True


def _safe_move(src: Path, dest: Path) -> None:
    if _same_volume(src, dest):
        shutil.move(str(src), str(dest))
        return
    _safe_copy(src, dest)
    src.unlink()


def _safe_copy(src: Path, dest: Path) -> None:
    shutil.copy2(src, dest)
    if dest.stat().st_size != src.stat().st_size:
        dest.unlink(missing_ok=True)
        raise _OpError(f"Copy verification failed for {src.name}.")


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
        raise _OpError(f"hook timed out after {deck.hook_timeout} seconds") from exc
    except OSError as exc:
        raise _OpError(f"hook could not start ({exc.strerror or exc})") from exc
    if result.returncode != 0:
        err = (result.stderr or result.stdout or b"").decode("utf-8", "replace").strip()
        err = err[-400:] if err else f"exit {result.returncode}"
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


def _plugin_handle(deck: Deck, item: Item, direction: str, note: str) -> dict:
    plugin = deck.plugin
    item_id = item.id
    if hasattr(plugin, "handle"):
        return dict(plugin.handle(item_id, direction, note=note) or {})
    from choice.swipe_plugin import SwipePlugin

    if isinstance(plugin, SwipePlugin):
        return plugin.handle(item_id, direction, note=note)
    return {"ok": True}


def _plugin_done(item: Item) -> bool:
    return bool(item.plugin_decided or item.fields.get("plugin_decided"))


def _plugin_message(raw) -> str:
    if raw is None:
        return ""
    text = str(raw).strip()
    return html.escape(text[:400])


def _plugin_error_text(exc: BaseException) -> str:
    return _plugin_message(exc) or "The plugin raised an error."


def _plugin_undo(deck: Deck, item_id: str, token: str | None) -> dict:
    plugin = deck.plugin
    if hasattr(plugin, "undo"):
        return dict(plugin.undo(item_id, token) or {})
    from choice.swipe_plugin import SwipePlugin

    if isinstance(plugin, SwipePlugin):
        return plugin.undo(item_id, token)
    return {"ok": True}


class _OpError(Exception):
    pass
