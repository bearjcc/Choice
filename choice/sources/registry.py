# SPDX-License-Identifier: AGPL-3.0-only
"""Source type registry."""

from __future__ import annotations

from choice.config import AppConfig, ConfigProblem, SourceSpec
from choice.sources.base import Source
from choice.sources.folder import FolderSource
from choice.sources.immich import ImmichSource
from choice.sources.rss import RssSource
from choice.sources.swipe import SwipeSource
from choice.sources.webdav import WebDavSource

_TYPES: dict[str, type[Source]] = {
    "folder": FolderSource,
    "swipe": SwipeSource,
    "swipe_plugin": SwipeSource,
    "ursala_swipe": SwipeSource,
    "immich": ImmichSource,
    "rss": RssSource,
    "atom": RssSource,
    "webdav": WebDavSource,
}


def source_types() -> list[dict[str, str]]:
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for key, cls in _TYPES.items():
        if cls in seen:
            continue
        seen.add(cls)
        out.append(
            {"type": key, "label": cls.__doc__.split("\n")[0].strip() if cls.__doc__ else key}
        )
    return out


def build_source(spec: SourceSpec, config: AppConfig) -> Source:
    cls = _TYPES.get(spec.type)
    if cls is None:
        raise ConfigProblem(f"Unknown source type {spec.type!r}.")
    return cls(spec.id, config, dict(spec.options))


def register_source(type_name: str, cls: type[Source]) -> None:
    _TYPES[type_name] = cls
