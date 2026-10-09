# SPDX-License-Identifier: AGPL-3.0-only
"""Swipe-compatible deck.py plugin folders."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from choice.config import ConfigProblem
from choice.deck_index import list_lock, record_items
from choice.folder_deck import apply_sort_direction_labels
from choice.load import Deck, DeckProblem, Direction, _directions as _config_directions
from choice.plugin_pool import get_plugin
from choice.sources.base import PreviewItem, Source
from choice.swipe_plugin import SwipePlugin, load_swipe_class, swipe_item_to_choice

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
            raise ConfigProblem(f"Mount {mount!r} escapes swipe decks root.")
        return folder

    def test(self) -> tuple[bool, str]:
        root = self._root()
        if not root.is_dir():
            return False, f"Decks folder not found: {root}"
        return True, f"OK ({root})"

    def preview(self, mount: str, limit: int = 5) -> list[PreviewItem]:
        try:
            plugin = self._load_plugin(mount, "preview")
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
        plugin = self._load_plugin(mount, deck_id)
        if deck_id != plugin.deck_id:
            plugin.deck_id = deck_id
        directions, buttons = _plugin_directions(plugin)
        directions = _merge_deck_option_directions(directions, deck_options)
        blind = bool(getattr(plugin.obj, "blind_default", False) or deck_options.get("blind"))
        folder = self._folder(mount)
        private_feed = bool(deck_options.get("private") or deck_options.get("notify") is False)

        def _load():
            warnings: list[str] = []
            with list_lock(deck_ref):
                try:
                    raw_items = plugin.list_items()
                except Exception as exc:
                    raise DeckProblem(str(exc)) from exc
            items = []
            for row in raw_items:
                if not isinstance(row, dict):
                    continue
                item_id = str(row.get("id") or "")
                if not item_id:
                    warnings.append("skipped item with no id")
                    continue
                item, row_notes = swipe_item_to_choice(row, folder, plugin)
                warnings.extend(row_notes)
                items.append(item)
            record_items(deck_ref, items)
            return items, warnings

        deck_ref = Deck(
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
            private_feed=private_feed,
        )
        return deck_ref

    def _load_plugin(self, mount: str, deck_id: str) -> SwipePlugin:
        folder = self._folder(mount)
        deck_py = folder / "deck.py"
        if not deck_py.is_file():
            raise ConfigProblem(f"No deck.py in {folder}")
        folder_id = folder.name
        pool_opts = {"mount": mount, "source": "swipe"}

        def loader():
            try:
                return load_swipe_class(deck_py, folder_id)
            except Exception as exc:
                raise ConfigProblem(f"Could not load {deck_py}: {exc}") from exc

        plugin = get_plugin(folder, deck_id, pool_opts, loader)
        if plugin.title != str(getattr(plugin.obj, "title", folder_id)):
            plugin.title = str(getattr(plugin.obj, "title", folder_id))
        return plugin


def _merge_deck_option_directions(
    directions: dict[str, Direction], deck_options: dict[str, Any]
) -> dict[str, Direction]:
    raw = deck_options.get("directions")
    if isinstance(raw, dict):
        for key, direction in _config_directions(raw).items():
            directions[key] = direction
    return apply_sort_direction_labels(directions, deck_options)


def _plugin_directions(plugin: SwipePlugin) -> tuple[dict[str, Direction], list[Direction]]:
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
