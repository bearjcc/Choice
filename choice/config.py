# SPDX-License-Identifier: AGPL-3.0-only
"""Load and save Choice configuration (TOML).

Secrets in config are env var names, never values. Optional ``secrets_file``
holds key/value lines for local dev; values are never logged or returned by API.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_SECRET_SUFFIX = ("_key", "_password", "_token", "_secret", "api_key", "password")


class ConfigProblem(Exception):
    """User-fixable config error."""


@dataclass
class SourceSpec:
    id: str
    type: str
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class DeckSpec:
    id: str
    title: str
    source: str
    mount: str
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class AppConfig:
    path: Path
    state_dir: Path
    sources: list[SourceSpec]
    decks: list[DeckSpec]
    secrets_file: Path | None = None
    roster_path: Path | None = None

    def source(self, source_id: str) -> SourceSpec | None:
        for spec in self.sources:
            if spec.id == source_id:
                return spec
        return None


def load_config(path: Path) -> AppConfig:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise ConfigProblem("No config file at %s" % path)
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigProblem("Invalid TOML in %s: %s" % (path, exc)) from exc
    if not isinstance(raw, dict):
        raise ConfigProblem("Config root must be a table.")

    state_block = raw.get("state") or {}
    if not isinstance(state_block, dict):
        raise ConfigProblem("[state] must be a table.")
    state_raw = state_block.get("dir") or ".choice-state"
    state_dir = _expand(state_raw, path.parent)

    secrets_raw = state_block.get("secrets_file")
    secrets_file = _expand(secrets_raw, path.parent) if secrets_raw else None

    roster_raw = state_block.get("users_file")
    roster_path = _expand(roster_raw, path.parent) if roster_raw else None

    sources: list[SourceSpec] = []
    for idx, row in enumerate(raw.get("sources") or raw.get("source") or []):
        sources.append(_parse_source(row, idx))

    decks: list[DeckSpec] = []
    for idx, row in enumerate(raw.get("decks") or raw.get("deck") or []):
        decks.append(_parse_deck(row, idx))

    if not decks and not sources:
        raise ConfigProblem("Config needs at least one [[sources]] and [[decks]] entry.")

    seen_src = set()
    for spec in sources:
        if spec.id in seen_src:
            raise ConfigProblem("Duplicate source id %r." % spec.id)
        seen_src.add(spec.id)

    seen_deck = set()
    for spec in decks:
        if spec.id in seen_deck:
            raise ConfigProblem("Duplicate deck id %r." % spec.id)
        seen_deck.add(spec.id)
        if spec.source not in seen_src:
            raise ConfigProblem("Deck %r points at unknown source %r." % (spec.id, spec.source))

    return AppConfig(
        path=path,
        state_dir=state_dir,
        sources=sources,
        decks=decks,
        secrets_file=secrets_file,
        roster_path=roster_path,
    )


def save_config(config: AppConfig, sources: list[dict], decks: list[dict]) -> None:
    """Write config; secret fields stay as env ref strings only."""
    lines = [
        "# Choice configuration. See choice.example.toml.",
        "",
        "[state]",
        'dir = "%s"' % _toml_str(str(config.state_dir)),
    ]
    if config.secrets_file:
        lines.append('secrets_file = "%s"' % _toml_str(str(config.secrets_file)))
    if config.roster_path:
        lines.append('users_file = "%s"' % _toml_str(str(config.roster_path)))
    lines.append("")
    for row in sources:
        lines.append("[[sources]]")
        for key, value in row.items():
            if key == "type":
                lines.append('type = "%s"' % _toml_str(str(value)))
            elif isinstance(value, bool):
                lines.append("%s = %s" % (key, "true" if value else "false"))
            elif isinstance(value, (int, float)):
                lines.append("%s = %s" % (key, value))
            else:
                lines.append('%s = "%s"' % (key, _toml_str(str(value))))
        lines.append("")
    for row in decks:
        lines.append("[[decks]]")
        for key, value in row.items():
            if isinstance(value, bool):
                lines.append("%s = %s" % (key, "true" if value else "false"))
            elif isinstance(value, (int, float)):
                lines.append("%s = %s" % (key, value))
            else:
                lines.append('%s = "%s"' % (key, _toml_str(str(value))))
        lines.append("")
    config.path.parent.mkdir(parents=True, exist_ok=True)
    config.path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def resolve_secret(name: str, config: AppConfig | None = None) -> str:
    """Look up a secret reference (env var name) or literal env-style name."""
    name = (name or "").strip()
    if not name:
        return ""
    if name in os.environ:
        return os.environ[name]
    if config and config.secrets_file and config.secrets_file.is_file():
        for line in config.secrets_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == name:
                return value.strip()
    return ""


def mask_secrets(row: dict) -> dict:
    out = {}
    for key, value in row.items():
        if _is_secret_key(key) and value:
            out[key] = "***"
        else:
            out[key] = value
    return out


def _parse_source(row: Any, idx: int) -> SourceSpec:
    if not isinstance(row, dict):
        raise ConfigProblem("sources[%d] must be a table." % idx)
    sid = str(row.get("id") or "").strip()
    if not _ID.match(sid):
        raise ConfigProblem("sources[%d] needs id ([a-z0-9_-])." % idx)
    typ = str(row.get("type") or "").strip().lower()
    if not typ:
        raise ConfigProblem("sources[%d] needs type." % idx)
    opts = {k: v for k, v in row.items() if k not in {"id", "type"}}
    return SourceSpec(id=sid, type=typ, options=opts)


def _parse_deck(row: Any, idx: int) -> DeckSpec:
    if not isinstance(row, dict):
        raise ConfigProblem("decks[%d] must be a table." % idx)
    did = str(row.get("id") or "").strip()
    if not _ID.match(did):
        raise ConfigProblem("decks[%d] needs id ([a-z0-9_-])." % idx)
    title = str(row.get("title") or did).strip()
    source = str(row.get("source") or "").strip()
    mount = str(row.get("mount") or row.get("path") or "").strip()
    if not source:
        raise ConfigProblem("decks[%d] needs source." % idx)
    opts = {k: v for k, v in row.items() if k not in {"id", "title", "source", "mount", "path"}}
    return DeckSpec(id=did, title=title, source=source, mount=mount, options=opts)


def _expand(raw: str, base: Path) -> Path:
    text = str(raw).strip()
    if text.startswith("~"):
        return Path(os.path.expanduser(text)).resolve()
    path = Path(text)
    if not path.is_absolute():
        path = (base / path).resolve()
    return path


def _is_secret_key(key: str) -> bool:
    low = key.lower()
    return any(low.endswith(s) or low == s for s in _SECRET_SUFFIX)


def _toml_str(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')
