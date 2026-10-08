# Changelog

## 0.2.0 (2026-10-08)

### Added

- Pluggable deck sources via `choice.toml` (`--config` / `CHOICE_CONFIG`): folder, Swipe `deck.py` plugins, Immich, RSS/Atom, WebDAV.
- Per-deck state directory separate from read-only sources.
- Folder source **results** vs **sort** output, recursion, include/exclude globs, sort target folders.
- Add-deck UI (config mode): sources/decks editor, connection test, preview, masked secrets via `POST /api/secrets`.
- Swipe engine ports: item cache (~1s), paged queue params, gzip JSON, media `?v=`, plugin `media_bytes`, stats endpoint, preload next images, A/B keys and click-to-pick.
- **rated** contest (Glicko-style pairs) and **taste** two-stage flow; JSON export with rankings.
- `GET /api/health`, `GET /api/decks/<id>/export`, `GET /api/decks/<id>/stats`.
- Examples: `taste`, `rated`. Tests for folder source, sources, and flows (34 tests).

### Changed

- A bare photo folder defaults to **results** mode (log only) instead of moving files to trash unless `deck.json` or sort mode says otherwise.

### Security

- Default bind remains `127.0.0.1`; `--lan` prints an explicit warning.
