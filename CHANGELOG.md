# Changelog

## 0.3.5 (2026-10-09)

### Fixed

- Sort file moves use `os.replace` on the same volume (no copy-and-delete fallback). Blocked renames stay queued with backoff until the source is gone.
- Cross-volume moves copy via a temp file, fsync, atomic rename, then require a successful source delete before the job completes.
- Reconcile removes identical source/destination duplicates, or renames conflicting destinations with a `.choice-conflict-*` suffix and logs to `move_conflicts.jsonl`.

### Tests

- Stranded duplicate after a partial move plus restart; locked source delete retries through reconcile.

## 0.3.4 (2026-10-09)

### Fixed

- Work queue keeps one in-memory job list per deck under a single lock; every enqueue, status change, and persist runs in that critical section so concurrent decides cannot be overwritten by a stale save.
- On deck boot, reconcile re-enqueues logged sort moves whose files are still at the source path and readmits them to the folder index.
- Folder index kicks a background scan at server boot and on the first home summary when the pile is still empty.

### Tests

- 300-thread decide burst and mid-burst memory drop with restart reconcile (log, disk, index).

## 0.3.3 (2026-10-09)

### Fixed

- Folder `/decide`, `/undo`, and `/media` no longer load the full pile; O(1) index lookup and a narrower decide lock.
- Sort destination folders are excluded from the index; moves remove pile ids instead of re-listing at the new path; already-decided ids cannot move again.
- `work_queue.json` uses a file lock, Windows-safe `atomic_replace`, prunes finished jobs, and supervises the mover thread.
- Home deck row shows "Scanning…" while the folder index is warming instead of misleading counts.

### Tests

- Sort-index smoke tests, version parity (`pyproject` vs `choice.__version__`), atomic replace retries, 30k async load with media 304 timing.

## 0.3.2 (2026-10-09)

### Added

- Queue badge on the deck screen (pending / failed counts); tap failed badge for error lines from `stats.queue.failures`.
- Client prefetches the next `/items` page when fewer than three cards remain in the buffer (limit 200).

### Fixed

- Folder `decide` resolves the card via `folder_index` instead of loading the full pile.

### Tests

- Async load test: 20k-file sort deck, 4 decides/s for 60s, p95 decide ≤ 30 ms, queue drain, log vs disk, undo before and after move.

## 0.3.1 (2026-10-09)

### Added

- Persistent async work queue for folder sort moves (sync in tests via `CHOICE_SYNC_WORK`).
- Incremental `folder_index.json`: stable append-only pile order, debounced background scans, non-blocking home counts with `stale`.

### Fixed

- `/api/index` no longer rescans the whole tree on every request; directory mtimes detect growth without listing every file.
- Folder `/items` pages from the index (default limit 200) without building all cards per request.

### Performance

- Large folder decks: index and first `/items` page stay fast while files are still being copied in.
- Plugin `/items` paging reuses the in-memory list snapshot when warm.

## 0.3.0 (2026-10-09)

### Added

- Remove deck from config UI (state and files on disk stay; roster updated).
- Fixed `/media` width buckets (640/960/1280/1600), optimistic swipes with rollback, image decode preload, deck hover prefetch, server media warm pool.
- Folder listing cache with invalidation; home counts for large folder decks without building cards; bounded LRU caches; config open cache.

### Performance

- Decision log snapshot cache; faster repeat API calls when `choice.toml` unchanged.

## 0.2.10 (2026-10-08)

### Fixed

- Plugin home rows: `total = decided + left` always; `decided` is log decisions plus plugin-decided items in the current list; `list_size` is the raw pile length.
- Upgrades old `list_counts.json` (no `ids`) by reloading the plugin list on first index read.

### Docs

- `docs/windows.md`: install from release zip with `pip install --no-cache-dir`.

## 0.2.9 (2026-10-08)

### Fixed

- **Immich paging**: fixed page size, dedupe asset ids, stop at limit (no duplicate cards across pages).
- **Immich visibility**: treat `visibility` of `hidden` or `locked`; favourite swipe is opt-in (`favourite = true`).
- **Home deck counts**: `decided` always matches the decision log; fresh index and persisted counts agree after restart.
- **Video cards**: Immich videos expose preview thumbnail on the phone (`media: true`).

### Docs

- README: install from release zip or wheel without polluting the app folder.

## 0.2.8 (2026-10-08)

### Fixed

- **Immich 3.2+**: album listing via metadata search, correct trash/restore APIs, WebP content types, `media_bytes` contract, `plugin_media`, smart/metadata search paging, asset filters.
- Release zips exclude egg-info and caches; example `.choice` state removed from the repo.

### Added

- `choice/web_paths.py` for frozen-friendly static assets; `tests/test_release_zip.py` guards release contents.

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
