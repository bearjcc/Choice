# Changelog

## 0.2.7 (2026-10-08)

### Added

- Phone-sized `/media` (WebP/JPEG, ~1600px long edge, optional `?w=`), disk cache with LRU sweep, `?full=1` for originals.
- Optional `images` extra (`Pillow`) for resizing; without Pillow, originals are served.

## 0.2.6 (2026-10-08)

### Fixed

- Plugin image paths: inside-deck checks apply to relative paths only; absolute paths allowed.
- Plugins with `media_bytes` keep non-file `image_path` / `images` tokens as media (as in 0.2.4).
- Home deck list shows last-known plugin counts from `list_counts.json` and warms counts in the background.

## 0.2.5 (2026-10-08)

### Fixed

- Swipe plugin `images` entries may be plain path strings; unresolved paths warn instead of disappearing.
- `image_path` uses the same path-safety checks; main photo falls back to the first resolved `images` entry.

## 0.2.4 (2026-10-08)

### Added

- Long-lived `deck.py` plugin instances (reload on `deck.py` mtime; shutdown hook on replace).
- Cheap deck-list counts for plugin decks via cached snapshots; per-deck lock around `list_items`.
- `media_bytes` receives the full item row; gallery cards with multiple photos; `GET /api/feed`.
- Plugin `decided` on items, `actions` + `POST /api/decks/<id>/action`, `private` / `notify = false` feed flag.
- Plugin errors surfaced on failed swipes without logging the decision.

## 0.2.3 (2026-10-08)

### Removed

- Swipe-specific `legacy_log` deck option and `python -m choice import` (use the standalone `swipe_to_choice.py` migrator instead).

### Added

- Config error when `legacy_log` is still present in `choice.toml`.

## 0.2.2 (2026-10-08)

### Added

- Swipe event log support for `swipe` decks: `legacy_log` (read-only merge during side-by-side) and `python -m choice import` (one-shot, idempotent copy into Choice's log).
- Plugin `handle`/`undo` idempotency: repeating the same Choice decision does not call the plugin twice.

### Fixed

- Decided counts and pending queues honour Swipe `swipe`/`undo` replay semantics (undone swipes drop out; last live swipe per item wins).

## 0.2.1 (2026-10-08)

### Added

- `--base-path` (and `CHOICE_BASE_PATH`) for reverse-proxy URL prefixes; API and static assets respect the prefix.

### Fixed

- Swipe drag no longer scrolls the page horizontally (clipped main stage, `touch-action: none` on cards).
- Deck list source icons use inline SVGs instead of letters.

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
- Phone-first swipe UI: four-way drag with on-card hints, floating undo, overflow menu, content-sized cards, neutral A/B, add-deck stepper, deck list cards. `GET /api/browse` for folder paths. Gesture helper tests.

### Changed

- Web UI: Tinder-style gestures on narrow viewports; action bar kept for keyboard and wide screens only.

- A bare photo folder defaults to **results** mode (log only) instead of moving files to trash unless `deck.json` or sort mode says otherwise.

### Security

- Default bind remains `127.0.0.1`; `--lan` prints an explicit warning.
