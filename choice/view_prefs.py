# SPDX-License-Identifier: AGPL-3.0-only
"""Per-deck pile order and filters (saved in state dir)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from choice.load import Deck

_PREFS_FILE = "view_prefs.json"
_SORT_MODES = frozenset(
    {"scan", "random", "mtime_desc", "mtime_asc", "folder", "filename"}
)


@dataclass
class ViewPrefs:
    sort_mode: str = "scan"
    random_seed: str = ""
    file_types: list[str] = field(default_factory=list)
    include_folders: list[str] = field(default_factory=list)
    exclude_folders: list[str] = field(default_factory=list)

    def fingerprint(self) -> str:
        blob = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        return {
            "sort_mode": self.sort_mode,
            "random_seed": self.random_seed,
            "file_types": list(self.file_types),
            "include_folders": list(self.include_folders),
            "exclude_folders": list(self.exclude_folders),
        }

    @staticmethod
    def from_dict(data: dict, defaults: ViewPrefs | None = None) -> ViewPrefs:
        base = defaults or ViewPrefs()
        mode = str(data.get("sort_mode") or base.sort_mode)
        if mode not in _SORT_MODES:
            mode = base.sort_mode
        seed = str(data.get("random_seed") if data.get("random_seed") is not None else base.random_seed)
        return ViewPrefs(
            sort_mode=mode,
            random_seed=seed,
            file_types=_str_list(data.get("file_types"), base.file_types),
            include_folders=_norm_folders(data.get("include_folders"), base.include_folders),
            exclude_folders=_norm_folders(data.get("exclude_folders"), base.exclude_folders),
        )


def pile_view_locked(deck: Deck) -> bool:
    if deck.story or deck.score_field or deck.contest_kind:
        return True
    if deck.plugin is not None and deck.folder_scan is None:
        return True
    return False


def defaults_for(deck: Deck) -> ViewPrefs:
    raw = getattr(deck, "view_defaults", None) or {}
    if not isinstance(raw, dict):
        raw = {}
    return ViewPrefs.from_dict(raw, ViewPrefs(random_seed=deck.id))


def prefs_path(state_dir: Path) -> Path:
    return state_dir / _PREFS_FILE


def load_view_prefs(deck: Deck) -> ViewPrefs:
    defaults = defaults_for(deck)
    if pile_view_locked(deck):
        return defaults
    path = prefs_path(deck.state_dir)
    if not path.is_file():
        return defaults
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return defaults
    if not isinstance(data, dict):
        return defaults
    return ViewPrefs.from_dict(data, defaults)


def save_view_prefs(deck: Deck, prefs: ViewPrefs) -> None:
    if pile_view_locked(deck):
        return
    path = prefs_path(deck.state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    from choice.atomic_io import write_json_atomic

    write_json_atomic(path, prefs.to_dict(), indent=2, trailing_newline=True)


def public_view(deck: Deck) -> dict:
    prefs = load_view_prefs(deck)
    return {
        "locked": pile_view_locked(deck),
        "prefs": prefs.to_dict(),
        "defaults": defaults_for(deck).to_dict(),
    }


def _str_list(value, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return list(fallback)
    return [str(x).strip().lower() for x in value if str(x).strip()]


def _norm_folders(value, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return list(fallback)
    out: list[str] = []
    for row in value:
        text = str(row).strip().replace("\\", "/").strip("/")
        if text:
            out.append(text)
    return out
