# SPDX-License-Identifier: AGPL-3.0-only
"""Source interface: list items, fetch media, optional actions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from choice.config import AppConfig
from choice.load import Deck


@dataclass
class PreviewItem:
    id: str
    title: str
    kind: str
    body: str = ""


class Source(ABC):
    """One connection (folder, Immich, RSS, …). Decks mount paths within it."""

    def __init__(self, spec_id: str, config: AppConfig, options: dict[str, Any]):
        self.spec_id = spec_id
        self.app_config = config
        self.options = options

    @abstractmethod
    def test(self) -> tuple[bool, str]:
        """Return (ok, message) for the add-deck UI."""

    @abstractmethod
    def preview(self, mount: str, limit: int = 5) -> list[PreviewItem]:
        """Sample items for connection test."""

    @abstractmethod
    def open_deck(
        self,
        deck_id: str,
        title: str,
        mount: str,
        state_dir: Path,
        deck_options: dict[str, Any],
    ) -> Deck:
        """Build a ready-to-swipe deck."""

    def resolve_mount(self, mount: str) -> str:
        return (mount or ".").strip() or "."
