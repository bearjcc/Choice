# SPDX-License-Identifier: AGPL-3.0-only
"""Swipe-compatible deck.py plugin folders."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from choice.config import ConfigProblem
from choice.load import Deck, Direction
from choice.sources.base import PreviewItem, Source
from choice.swipe_plugin import SwipePlugin, load_swipe_class, swipe_item_to_choice

_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_DIRS = ("left", "right", "up", "down")


class SwipeSource(Source):
    def _root(self) -> Path:
        raw = self.options.get("path") or self.options.get("root") or "."
        base = self.app_config.path.parent
        path = Path(str(raw)).expanduser()
        if not path.is_absolute():
            path = (base / path).resolve()
        return path.resolve()

    def _folder(self, mount: str) -> Path:
        root = self._root()
        name = self.resolve_mount(mount)
        folder = (root / name).resolve()
        try:
            folder.relative_to(root)
        except ValueError:
            raise ConfigProblem("Mount %r escapes swipe decks root." % mount)
        return folder

    def test(self) -> tuple[bool, str]:
        root = self._root()
        if not root.is_dir():
            return False, "Decks folder not found: %s" % root
        return True, "OK (%s)" % root

    def preview(self, mount: str, limit: int = 5) -> list[PreviewItem]:
        try:
            plugin = self._load_plugin(mount)
        except ConfigProblem:
            return []
        try:
            raw_items = plugin.list_items()
        except Exception:
            return []
        out: list[PreviewItem] = []
        for row in raw_items[:limit]:
            if not isinstance(row, dict):
                continue
            out.append(
                PreviewItem(
                    id=str(row.get("id") or ""),
                    title=str(row.get("title") or row.get("id") or ""),
                    kind=str(row.get("kind") or "card"),
                    body=str(row.get("body") or "")[:200],
                )
            )
        return out

    def open_deck(
        self,
        deck_id: str,
        title: str,
        mount: str,
        state_dir: Path,
        deck_options: dict[str, Any],
    ) -> Deck:
        plugin = self._load_plugin(mount)
        if deck_id != plugin.deck_id:
            plugin.deck_id = deck_id
        directions, buttons = _directions(plugin)
        blind = bool(getattr(plugin.obj, "blind_default", False) or deck_options.get("blind"))
        folder = self._folder(mount)

        def _load():
            rows = plugin.list_items(filter=deck_options.get("filter"))
            items = []
            warnings: list[str] = []
            for row in rows:
                try:
                    items.append(swipe_item_to_choice(row, folder, plugin))
                except Exception as exc:
                    warnings.append("%s: %s" % (row.get("id"), exc))
            return items, warnings

        return Deck(
            id=deck_id,
            title=title or plugin.title,
            root=folder,
            state_dir=state_dir,
            directions=directions,
            buttons=buttons,
            blind=blind,
            warnings=[],
            _load=_load,
            plugin=plugin,
        )

    def _load_plugin(self, mount: str) -> SwipePlugin:
        folder = self._folder(mount)
        deck_py = folder / "deck.py"
        if not deck_py.is_file():
            raise ConfigProblem("No deck.py in %s" % folder)
        folder_id = folder.name
        try:
            obj = load_swipe_class(deck_py, folder_id)
        except Exception as exc:
            raise ConfigProblem("Could not load %s: %s" % (deck_py, exc)) from exc
        return SwipePlugin(obj=obj, folder=folder, deck_id=folder_id, title=str(getattr(obj, "title", folder_id)))


def _directions(plugin: SwipePlugin) -> tuple[dict[str, Direction], list[Direction]]:
    raw = getattr(plugin.obj, "directions", None) or {}
    directions: dict[str, Direction] = {}
    for key in _DIRS:
        if key not in raw:
            continue
        spec = raw[key]
        if not isinstance(spec, dict):
            continue
        directions[key] = Direction(
            id=key,
            label=str(spec.get("label") or key),
            value=str(spec.get("value") or spec.get("label") or key),
            later=bool(spec.get("later")),
            does="label",
            color=spec.get("color"),
        )
    buttons: list[Direction] = []
    for spec in getattr(plugin.obj, "extra_buttons", None) or []:
        if not isinstance(spec, dict):
            continue
        bid = str(spec.get("id") or "")
        if not bid:
            continue
        buttons.append(
            Direction(
                id=bid,
                label=str(spec.get("label") or bid),
                value=str(spec.get("value") or spec.get("label") or bid),
                later=bool(spec.get("later")),
                does="label",
                color=spec.get("color"),
            )
        )
    return directions, buttons
