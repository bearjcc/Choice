# SPDX-License-Identifier: AGPL-3.0-only
"""Open decks from a config file or a legacy folder path."""

from __future__ import annotations

import logging
from pathlib import Path

from choice.config import ConfigProblem, load_config

_log = logging.getLogger(__name__)
from choice.load import Deck, DeckProblem, Opened, resolve
from choice.sources.registry import build_source


def open_path(path: Path) -> Opened:
    path = path.expanduser()
    if path.is_file() and path.suffix.lower() in {".toml", ".json"}:
        return open_config(path)
    return resolve(path.resolve())


def open_config(path: Path) -> Opened:
    config = load_config(path)
    config.state_dir.mkdir(parents=True, exist_ok=True)
    sources = {spec.id: build_source(spec, config) for spec in config.sources}
    decks: list[Deck] = []
    for spec in config.decks:
        source = sources.get(spec.source)
        if source is None:
            raise ConfigProblem(f"Deck {spec.id!r}: unknown source {spec.source!r}.")
        state_dir = config.state_dir / spec.id
        state_dir.mkdir(parents=True, exist_ok=True)
        try:
            deck = source.open_deck(spec.id, spec.title, spec.mount, state_dir, dict(spec.options))
        except (ConfigProblem, DeckProblem) as exc:
            _log.warning("Deck %s skipped: %s", spec.id, exc)
            decks.append(_problem_deck(spec, state_dir, str(exc)))
            continue
        except Exception as exc:
            _log.exception("Deck %s failed to open", spec.id)
            decks.append(_problem_deck(spec, state_dir, str(exc)))
            continue
        contest = spec.options.get("contest")
        if contest:
            deck.contest_kind = str(contest)
        if spec.options.get("taste"):
            deck.contest_kind = "taste"
        if spec.options.get("rated"):
            deck.contest_kind = "rated"
        if spec.options.get("private") or spec.options.get("notify") is False:
            deck.private_feed = True
        src_spec = config.source(spec.source)
        if src_spec is not None:
            deck.source_type = src_spec.type
        counts_raw = spec.options.get("counts")
        if counts_raw is not None and deck.counts_defaults is None:
            deck.counts_defaults = counts_raw
        if spec.options.get("allow_undo") is False or spec.options.get("undo") is False:
            deck.allow_undo = False
        if spec.options.get("show_filename") is True:
            deck.show_filename = True
        decks.append(deck)
    return Opened(decks=decks, direct=False)


def _problem_deck(spec, state_dir: Path, message: str) -> Deck:
    return Deck(
        id=spec.id,
        title=spec.title,
        root=state_dir,
        state_dir=state_dir,
        directions={},
        buttons=[],
        blind=False,
        warnings=[],
        problem=message,
        _load=lambda: ([], []),
    )


def config_root(path: Path) -> Path:
    """Path stored on the HTTP server for roster/config lookups."""
    path = path.expanduser().resolve()
    if path.is_file():
        return path.parent
    return path
