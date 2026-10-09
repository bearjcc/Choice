# Changelog

## 0.4.8 (2026-10-09)

### Fixed

- Folder `progress_page` empty-pile counts use `(total, decided, left)` correctly; `scanning` only when indexed paths vanished, not when a sort pile is finished.
- Home and `/items` share folder view-filtered counts and plugin log universe (including when the in-memory snapshot expired).
- Offset paging exposes `next_offset` past the first 200 cards.

## 0.4.7 (2026-10-09)

### Fixed

- Phone modals and sheets: viewport-fixed layout with safe-area and `visualViewport` when the keyboard opens, internal scroll, body scroll lock, backdrop tap and Escape; in-app confirms replace `window.confirm` for deck remove and plugin actions.
- Headless layout checks at 360×640, 390×844, and landscape 844×390 for menu, counts, sort/filter, count display, queue failures, assign, browse picker, and confirm.
- Folder `/items` decided counts follow the decision log on sort decks (`total == decided + left`); vanished index paths return `scanning: true` until rescan.
- “Decisions today” ignores undone swipes; plugin home `left` matches pending `/items`; scan completion busts item and list caches so new cards appear with counts.

## 0.4.6 (2026-10-09)

### Fixed

- Plugin hot reload: `/api/reload` and file watching purge the plugin pool, swipe modules, item and page caches, and warm scheduling; `deck.py` loads from source with pyc dropped and a content-hash fingerprint (not mtime alone).
- Folder rescan: debounced scans also run after at most five seconds of continuous `/items` polling so adds and deletes are not starved.

## 0.4.5 (2026-10-09)

### Fixed

- Undo while a sort move is still running: `cancel_requested` on running jobs, rollback after rename, reverse jobs wait for forward work.
- Plugin pending `/items` respects `decided`; cursor paging (`after=`); same-direction decide is idempotent; refused decides logged to `rejects.jsonl`; deck mismatch returns 409; pair `media_bytes` receives `side`.
- Folder index prunes vanished paths on scan; `total = decided + left`; readmit idempotent and serialized with `apply_move`.
- Pair cards: per-deck `pair_layout` (`auto`, `stack`, `side_by_side`) for narrow screens.

## 0.4.4 (2026-10-09)

### Fixed

- Work queue retries sleep outside the lock via `retry_after` and a condition wake; file-in-use backoff 1–30 s then minutes.
- Media cache writes use per-key locks and tolerate Windows replace races.
- Index readmit idempotent; concurrent readmit/apply_move cannot duplicate paths.

## 0.4.3 (2026-10-09)

### Fixed

- Failed file moves retry while the source remains (slow backoff, no terminal cap for sharing errors); boot revives failed jobs and reconcile no longer treats `failed` as blocking.
- In-process media read tracking so moves wait for `/media` and thumbnail encoding; queue badge shows pending or retrying.

## 0.4.2 (2026-10-09)

### Fixed

- Undo readmits sort cards to the front of the pending pile (and pins them for paginated `/items`) so large decks keep the restored card on the first page in scan and random order.
- Sort `decide` writes the decision log before enqueueing the move and updating the index; boot reconciles queue jobs that have no matching decision by reversing the index change.

## 0.4.1 (2026-10-09)

### Changed

- Swipe deck UI: fixed bottom action bar (deck choices plus undo when allowed). Card tap no longer opens a menu; sub-threshold taps and drags spring back only.
- Notes removed from the swipe UI (decide requests no longer send a note field from the browser).
- Filenames hidden on swipe cards by default; opt in per deck with `show_filename = true` in `deck.json` or `choice.toml`.

## 0.4.0 (2026-10-09)

### Added

- Per-deck pile order and filters for folder swipe and sort decks: sort modes (scan, natural filename, folder groups, mtime, stable random), file-type and folder include/exclude filters.
- Defaults in `deck.json` / `choice.toml` (`view` table or keys); UI changes save to `view_prefs.json` in the deck state dir.
- Sort metadata cached in `folder_index.json`; view order cached in memory without rescanning.
- Deck menu: Order and filter (hidden when contest, score, story, or plugin order is fixed).
- Optimistic undo: restored card returns immediately with a reverse-swipe animation; failed server undo reverts. `undo_hint` on deck payloads for re-anchoring after reload.
- Per-deck `allow_undo` (or `undo = false`) for quizzes and story decks; hides undo in the UI and rejects server undo.
- Per-deck count display: `auto`, `on`, or `off` (default in `deck.json` / `choice.toml` as `counts` or `view.counts`; override in `counts_prefs.json`). Auto hides totals for large piles, RSS, Elo (`rated`), story, and endless plugin decks; shows a optional “decisions today” label instead. Home and summary skip scan work when counts are hidden (`folder_stats.json` tracks pile size).

### Fixed

- Legacy folder listing uses natural sort so `12` orders before `117`.
- Sort moves refresh directory mtimes in the index instead of marking the tree outdated; home counts stay visible during background scans (`N left · scanning`).

## 0.3.7 (2026-10-09)

### Fixed

- Sort move planning reserves destination paths under the work-queue lock (disk plus pending/running jobs). Execution picks a new unique name when the path is taken; jobs are not done until the source is gone. Reconcile replans logged moves whose source remains and whose destination is missing or holds another file.

### Tests

- Concurrent same-name files across folders with kill/restart; reconcile after a falsely completed collision.

## 0.3.6 (2026-10-09)

### Fixed

- Still-to-do mode no longer skips a card after each swipe when the pending list reloads; pile cursor follows the on-screen card through reload, prefetch, and undo (`pile_nav.js`).

### Tests

- Headless `pile_nav` tests: single and double swipe before reload, show-all mode, undo anchor.

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
