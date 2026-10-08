# SPDX-License-Identifier: AGPL-3.0-only
"""Open decks from a config file or a legacy folder path."""

from __future__ import annotations

from pathlib import Path

from choice.config import ConfigProblem, load_config
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
            decks.append(
                Deck(
                    id=spec.id,
                    title=spec.title,
                    root=state_dir,
                    state_dir=state_dir,
                    directions={},
                    buttons=[],
                    blind=False,
                    warnings=[],
                    problem=str(exc),
                    _load=lambda: ([], []),
                )
            )
            continue
        contest = spec.options.get("contest")
        if contest:
            deck.contest_kind = str(contest)
        if spec.options.get("taste"):
            deck.contest_kind = "taste"
        if spec.options.get("rated"):
            deck.contest_kind = "rated"
        decks.append(deck)
    return Opened(decks=decks, direct=False)


def config_root(path: Path) -> Path:
    """Path stored on the HTTP server for roster/config lookups."""
    path = path.expanduser().resolve()
    if path.is_file():
        return path.parent
    return path
