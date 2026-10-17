# SPDX-License-Identifier: AGPL-3.0-only
"""Adapter for Swipe deck.py plugins inside Choice."""

from __future__ import annotations

import importlib.util
import inspect
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from choice.load import Item, Side, inside


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

    def media_bytes(
        self,
        item_id: str,
        item: dict | None = None,
        index: int | None = None,
        side: str | None = None,
    ) -> tuple[bytes, str] | None:
        fn = getattr(self.obj, "media_bytes", None)
        if not callable(fn):
            return None
        row = item if item is not None else {"id": item_id}
        result = None
        if side and _accepts(fn, "side"):
            if index is not None and _accepts(fn, "n"):
                result = fn(row, side=side, n=index)
            else:
                result = fn(row, side=side)
        elif index is not None and _accepts(fn, "n"):
            result = fn(row, n=index)
        elif _accepts(fn, "item_id") and not _accepts(fn, "n") and item is None:
            result = fn(item_id)
        else:
            try:
                result = fn(row)
            except TypeError:
                result = fn(item_id)
        if not result:
            return None
        if isinstance(result, tuple) and len(result) == 2:
            return bytes(result[0]), str(result[1])
        if isinstance(result, bytes):
            return result, "application/octet-stream"
        return None

    def filters(self) -> dict | None:
        fn = getattr(self.obj, "filters", None)
        if not callable(fn):
            return None
        try:
            raw = fn()
        except Exception:
            return None
        return dict(raw) if isinstance(raw, dict) else None

    def stats(self, filter: dict | None = None) -> dict | None:
        fn = getattr(self.obj, "stats", None)
        if not callable(fn):
            return None
        try:
            if filter is not None and _accepts(fn, "filter"):
                return dict(fn(filter=filter) or {})
            return dict(fn() or {})
        except Exception:
            return None

    def run_action(self, action_id: str) -> dict:
        fn = getattr(self.obj, "run_action", None)
        if not callable(fn):
            return {"ok": False, "message": "No such action."}
        return dict(fn(action_id) or {})


def purge_swipe_modules(prefix: str = "choice_swipe_") -> None:
    importlib.invalidate_caches()
    for name in list(sys.modules):
        if name.startswith(prefix):
            del sys.modules[name]


def _drop_pyc(deck_py: Path) -> None:
    try:
        pyc = importlib.util.cache_from_source(str(deck_py.resolve()))
        Path(pyc).unlink(missing_ok=True)
    except (OSError, ValueError):
        return


def load_swipe_class(deck_py: Path, folder_id: str) -> Any:
    deck_py = deck_py.resolve()
    mod_name = "choice_swipe_" + folder_id
    sys.modules.pop(mod_name, None)
    _drop_pyc(deck_py)
    importlib.invalidate_caches()
    spec = importlib.util.spec_from_file_location(mod_name, deck_py)
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


def _parse_reveal(row: dict) -> list[tuple[str, str]]:
    raw = row.get("reveal")
    if raw is None:
        return []
    if isinstance(raw, dict):
        out: list[tuple[str, str]] = []
        for key, value in raw.items():
            if value is None or value == "":
                continue
            out.append((str(key), str(value)))
        return out
    if isinstance(raw, list):
        out = []
        for entry in raw:
            if isinstance(entry, dict):
                label = str(entry.get("label") or entry.get("key") or "Answer")
                text = str(entry.get("text") or entry.get("value") or "")
                if text:
                    out.append((label, text))
            elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
                out.append((str(entry[0]), str(entry[1])))
        return out
    return []


def _parse_sections(row: dict) -> list[dict]:
    out: list[dict] = []
    raw = row.get("sections")
    if not isinstance(raw, list):
        return out
    for sec in raw:
        if not isinstance(sec, dict):
            continue
        out.append(
            {
                "title": str(sec.get("title") or ""),
                "text": str(sec.get("text") or ""),
                "collapsed": bool(sec.get("collapsed")),
                "main": bool(sec.get("main")),
            }
        )
    return out


def _ab_side_body(side: dict) -> str:
    return str(side.get("body") or side.get("text") or "")


def _ab_side_image_ref(side: dict) -> str | None:
    ref = side.get("image_path") or side.get("image")
    if ref is None or ref == "":
        return None
    return str(ref)


def swipe_item_to_choice(row: dict, folder: Path, plugin: SwipePlugin) -> tuple[Item, list[str]]:
    kind = str(row.get("kind") or "card")
    item_id = str(row.get("id") or "")
    title = str(row.get("title") or item_id)
    subtitle = str(row.get("subtitle") or "")
    body = str(row.get("body") or subtitle or "")
    plugin_decided = bool(row.get("decided"))
    fields = dict(row.get("fields") or {})
    notes: list[str] = []
    plugin_serves = _plugin_serves_media(plugin)
    chips = []
    for key, value in fields.items():
        if isinstance(value, (str, int, float, bool)):
            chips.append((str(key), str(value)))
    path = None
    media_token = ""
    plugin_media = False
    images: list[dict] = []
    raw_images = row.get("images") or []
    if isinstance(raw_images, list) and raw_images:
        for idx, img in enumerate(raw_images):
            caption = ""
            token = str(idx)
            if isinstance(img, str):
                rel = img
            elif isinstance(img, dict):
                rel = img.get("path") or img.get("file") or ""
                caption = str(img.get("caption") or "")
                token = str(img.get("token") or img.get("media_token") or idx)
            else:
                notes.append(f"{item_id}: images[{idx}] is not a path or object (skipped)")
                continue
            keep, ref, file_path, warn = _resolve_plugin_image_ref(
                folder, str(rel), item_id, idx, plugin_serves
            )
            if warn:
                notes.append(warn)
            if not keep:
                continue
            stored = str(file_path) if file_path is not None else ref
            if file_path is None and plugin_serves:
                plugin_media = True
            images.append(
                {
                    "path": stored,
                    "caption": caption,
                    "media_token": token or ref,
                }
            )
        if images:
            first_path = images[0]["path"]
            candidate = Path(first_path)
            if candidate.is_file():
                path = candidate
                media_token = images[0]["media_token"]
            elif plugin_serves:
                plugin_media = True
                media_token = images[0]["media_token"] or first_path
    image_path = row.get("image_path")
    if path is None and image_path:
        keep, ref, file_path, warn = _resolve_plugin_image_ref(
            folder, str(image_path), item_id, -1, plugin_serves
        )
        if warn:
            notes.append(warn)
        if keep:
            if file_path is not None:
                path = file_path
                media_token = ref
            elif plugin_serves:
                plugin_media = True
                media_token = ref
            if kind == "card":
                kind = "image"
    elif path is None and row.get("file"):
        path = folder / str(row["file"])
    if path and path.is_file():
        media_token = media_token or path.name
    elif plugin_media and not media_token:
        media_token = item_id
    if len(images) > 1 or kind == "profile":
        kind = "gallery"
    sides: list[Side] = []
    sections = _parse_sections(row)
    if kind == "pair" or row.get("ab"):
        ab = row.get("ab") or {}
        for key in ("a", "b"):
            side = ab.get(key) or {}
            side_body = _ab_side_body(side)
            img_ref = _ab_side_image_ref(side)
            side_path: Path | None = None
            side_token = ""
            if img_ref:
                keep, ref, file_path, warn = _resolve_plugin_image_ref(
                    folder, img_ref, item_id, -1, plugin_serves
                )
                if warn:
                    notes.append(warn)
                if keep:
                    side_token = ref
                    if file_path is not None:
                        side_path = file_path
                    elif plugin_serves:
                        side_path = None
                        side_token = ref or img_ref
            sides.append(
                Side(
                    key=key,
                    label=str(side.get("label") or key.upper()),
                    body=side_body,
                    path=side_path,
                    media_token=side_token,
                )
            )
        kind = "pair"
    if kind == "profile":
        fields["profile"] = True
    reveal = _parse_reveal(row)
    return (
        Item(
            id=item_id,
            kind=kind,
            title=title,
            body=body,
            chips=chips,
            reveal=reveal,
            path=path,
            media_token=media_token or item_id,
            fields=fields,
            sides=sides,
            plugin_decided=plugin_decided,
            plugin_row=dict(row),
            images=images,
            plugin_media=plugin_media,
            sections=sections,
        ),
        notes,
    )


def _plugin_serves_media(plugin: SwipePlugin) -> bool:
    return callable(getattr(plugin.obj, "media_bytes", None))


def _resolve_plugin_image_ref(
    folder: Path,
    text: str,
    item_id: str,
    idx: int,
    plugin_serves: bool,
) -> tuple[bool, str, Path | None, str | None]:
    """Return keep, ref string, optional local file path, optional warning."""
    label = "image_path" if idx < 0 else f"images[{idx}]"
    ref = str(text or "").strip()
    if not ref:
        return False, "", None, f"{item_id}: {label} is empty"
    parts = Path(ref.replace("\\", "/")).parts
    raw = Path(ref)
    if not raw.is_absolute():
        if ".." in parts:
            return False, "", None, f"{item_id}: {label} escapes deck ({ref})"
        root = folder.resolve()
        candidate = (folder / ref).resolve()
        if not inside(root, candidate):
            return False, "", None, f"{item_id}: {label} outside deck ({ref})"
        if candidate.is_symlink():
            return False, "", None, f"{item_id}: skipped symlink {label} ({ref})"
        if candidate.is_file():
            return True, ref, candidate, None
        if plugin_serves:
            return True, ref, None, None
        return False, "", None, f"{item_id}: image missing {label} ({ref})"
    candidate = raw.resolve()
    if candidate.is_file():
        return True, ref, candidate, None
    if plugin_serves:
        return True, ref, None, None
    return False, "", None, f"{item_id}: image missing {label} ({ref})"


def _accepts(fn, name: str) -> bool:
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return False
    for param in sig.parameters.values():
        if param.name == name:
            return True
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            return True
    return False
