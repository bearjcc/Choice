# SPDX-License-Identifier: AGPL-3.0-only
"""Adapter for Swipe deck.py plugins inside Choice."""

from __future__ import annotations

import importlib.util
import inspect
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from choice.load import Item, Side


@dataclass
class SwipePlugin:
    obj: Any
    folder: Path
    deck_id: str
    title: str

    def list_items(self, filter: dict | None = None) -> list[dict]:
        fn = self.obj.list_items
        if _accepts(fn, "filter"):
            return list(fn(filter=filter or {}))
        return list(fn())

    def handle(self, item_id: str, direction: str, note: str = "") -> dict:
        fn = self.obj.handle
        if _accepts(fn, "note"):
            return dict(fn(item_id, direction, note=note) or {})
        return dict(fn(item_id, direction) or {})

    def undo(self, item_id: str, undo_token: str | None) -> dict:
        fn = getattr(self.obj, "undo", None)
        if not callable(fn):
            return {"ok": True, "message": "Nothing to undo."}
        return dict(fn(item_id, undo_token) or {})

    def media_bytes(self, item_id: str) -> tuple[bytes, str] | None:
        fn = getattr(self.obj, "media_bytes", None)
        if not callable(fn):
            return None
        result = fn(item_id)
        if not result:
            return None
        if isinstance(result, tuple) and len(result) == 2:
            return bytes(result[0]), str(result[1])
        if isinstance(result, bytes):
            return result, "application/octet-stream"
        return None

    def stats(self) -> dict | None:
        fn = getattr(self.obj, "stats", None)
        if not callable(fn):
            return None
        try:
            return dict(fn() or {})
        except Exception:
            return None

    def run_action(self, action_id: str) -> dict:
        fn = getattr(self.obj, "run_action", None)
        if not callable(fn):
            return {"ok": False, "message": "No such action."}
        return dict(fn(action_id) or {})


def load_swipe_class(deck_py: Path, folder_id: str) -> Any:
    spec = importlib.util.spec_from_file_location("choice_swipe_" + folder_id, deck_py)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {deck_py}")
    mod = importlib.util.module_from_spec(spec)
    parent = str(deck_py.parent)
    sys.path.insert(0, parent)
    try:
        spec.loader.exec_module(mod)
    finally:
        if parent in sys.path:
            sys.path.remove(parent)
    if isinstance(getattr(mod, "Deck", None), type):
        return mod.Deck()
    for value in vars(mod).values():
        if (
            isinstance(value, type)
            and value.__module__ == mod.__name__
            and hasattr(value, "list_items")
            and hasattr(value, "handle")
        ):
            return value()
    raise RuntimeError(f"No Deck class in {deck_py}")


def swipe_item_to_choice(row: dict, folder: Path, plugin: SwipePlugin) -> Item:
    kind = str(row.get("kind") or "card")
    item_id = str(row.get("id") or "")
    title = str(row.get("title") or item_id)
    body = str(row.get("body") or "")
    fields = dict(row.get("fields") or {})
    chips = []
    for key, value in fields.items():
        if isinstance(value, (str, int, float, bool)):
            chips.append((str(key), str(value)))
    path = None
    media_token = ""
    image_path = row.get("image_path")
    if image_path:
        path = Path(str(image_path))
    elif row.get("file"):
        path = folder / str(row["file"])
    if path and path.is_file():
        media_token = path.name
    sides: list[Side] = []
    if kind == "pair" or row.get("ab"):
        ab = row.get("ab") or {}
        for key in ("a", "b"):
            side = ab.get(key) or {}
            sides.append(
                Side(
                    key=key,
                    label=str(side.get("label") or key.upper()),
                    body=str(side.get("body") or ""),
                    path=Path(str(side["image_path"])) if side.get("image_path") else None,
                )
            )
        kind = "pair"
    if kind == "profile":
        kind = "card"
        fields["profile"] = True
    return Item(
        id=item_id,
        kind=kind,
        title=title,
        body=body,
        chips=chips,
        reveal=[],
        path=path,
        media_token=media_token or item_id,
        fields=fields,
        sides=sides,
    )


def _accepts(fn, name: str) -> bool:
    try:
        return name in inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False
