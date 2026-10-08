# SPDX-License-Identifier: AGPL-3.0-only
"""Local folder source (deck.json, items files, or image piles)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from choice.config import ConfigProblem
from choice.folder_deck import (
    build_file_deck,
    items_from_folder_scan,
    merge_folder_options,
    wire_sort_buttons,
    wire_sort_directions,
)
from choice.load import Deck, DeckProblem, inside, resolve
from choice.sources.base import PreviewItem, Source


class FolderSource(Source):
    def _root(self) -> Path:
        raw = self.options.get("path") or self.options.get("root") or "."
        base = self.app_config.path.parent
        path = Path(str(raw)).expanduser()
        if not path.is_absolute():
            path = (base / path).resolve()
        else:
            path = path.resolve()
        return path

    def _deck_path(self, mount: str) -> Path:
        root = self._root()
        mount = self.resolve_mount(mount)
        target = (root / mount).resolve()
        if not inside(root, target) and target != root.resolve():
            raise ConfigProblem("Mount %r escapes source folder." % mount)
        return target

    def test(self) -> tuple[bool, str]:
        root = self._root()
        if not root.is_dir():
            return False, "Folder not found: %s" % root
        return True, "OK (%s)" % root

    def preview(self, mount: str, limit: int = 5) -> list[PreviewItem]:
        try:
            import tempfile

            deck = self.open_deck("preview", "Preview", mount, Path(tempfile.gettempdir()) / "choice-preview", {})
        except (ConfigProblem, DeckProblem):
            return []
        try:
            items, _warnings = deck.load_items()
        except DeckProblem:
            return []
        return [PreviewItem(id=i.id, title=i.title, kind=i.kind, body=i.body[:200]) for i in items[:limit]]

    def open_deck(
        self,
        deck_id: str,
        title: str,
        mount: str,
        state_dir: Path,
        deck_options: dict[str, Any],
    ) -> Deck:
        path = self._deck_path(mount)
        if (path / "deck.json").is_file():
            try:
                opened = resolve(path)
            except DeckProblem as exc:
                raise ConfigProblem(str(exc)) from exc
            if len(opened.decks) != 1:
                raise ConfigProblem("Mount %r is a library, not a single deck." % mount)
            deck = opened.decks[0]
            deck.id = deck_id
            deck.title = title or deck.title
            deck.state_dir = state_dir
            deck.root = path.resolve()
            data = json.loads((path / "deck.json").read_text(encoding="utf-8"))
            src = data.get("source") if isinstance(data.get("source"), dict) else {}
            scan = merge_folder_options({**src, **deck_options, "type": src.get("type") or "files"}, deck_options)
            deck.folder_scan = scan
            if scan.output == "sort":
                deck.directions = wire_sort_directions(deck.directions, scan.sort_targets)
                deck.buttons = wire_sort_buttons(deck.buttons, scan.sort_targets)

            def load_files():
                rel = str(src.get("path") or ".")
                target = path if rel in {".", ""} else (path / rel).resolve()
                return items_from_folder_scan(deck.root, target, scan), []

            if str(src.get("type") or "files") in {"files", "images"}:
                deck._load = load_files
            return deck

        merged = {**self.options, **deck_options}
        merged.setdefault("type", "files")
        return build_file_deck(path, deck_id, title or path.name, state_dir, merged)
