# Changelog

## 0.6.7 (2026-10-16)

### Changed

- Plugin A/B cards: `text` and `image` aliases on `ab` sides; `sections` render as collapsible context blocks (shared above pair sides). Wide layout (~900px+) respects `pair_layout`; gallery photos swap in place with fixed aspect ratio, tap zones, and preload.
- Plugin decks without valid `directions` get default No / Yes / Skip (server warning). Client always shows action bar and arrow-key shortcuts from deck directions with the same defaults.
- Plugin `reveal` (e.g. voice_whichone answers) is stored server-side but omitted from `/items` until a card is decided; `/decide` returns `reveal` and the UI shows it only after decide (pair cards included).

### Fixed

- `paintPair` respects blind mode; top-level `body` is not duplicated when `ab` is present. Gallery chips no longer render twice.

## 0.6.6 (2026-10-14)

### Fixed

- `save_index` no longer bails out before `mkdir` when the state directory does not exist yet (restores 0.6.4 behavior and fixes false “tree outdated” after sort decides).
- `apply_move` refreshes the deck root directory mtime when child paths change so `_tree_dirs_changed` stays accurate after file moves.

## 0.6.5 (2026-10-14)

### Fixed

- CI: Immich mock HTTP server uses HTTP/1.0, `Connection: close`, and flushed bodies on a single-thread `HTTPServer` to avoid Windows `ConnectionAbortedError` (WinError 10053) during paged search tests.
- Folder index perf test waits for background scans before teardown; `atomic_replace` handles a missing destination directory without leaving temp files; index saves ignore writes after state dir removal.

### Changed

- Folder index perf regression skips the default GitHub Actions matrix; same p95 assertions run in a dedicated `perf` CI job when `CHOICE_RUN_PERF=1`.

## 0.6.4 (2026-10-14)

### Changed

- Undo overhaul: session undo stack (full card, direction, later, decision id); optimistic restore at the current pile position in pending and show-all modes; media blob cache ~30 cards with revoke; saves and undos on an ordered queue so `/undo` sends `{item, decision_id}` only after earlier decides settle; `showSeq` so the newest items reload wins.
- `mergeReloadItems` pins a client-restored card when the server omits it or lists it later (stable undo across plugin `list_items` reorder).

### Fixed

- Show-all undo splices the card back instead of only re-anchoring; reconcile uses the restored card id.
- `openDeck` resets `pending` to true.
- Undo no longer posts `{}` while a decide is in flight.
- Server: plugin undo `ok: false` on later / `plugin_noop` decisions is treated as success so the log entry is not stuck.

### Tests

- Regression: show-all restore, merge pin, client queue/`decision_id`, plugin noop undo, targeted `decision_id`, later/skip undo.

## 0.6.3 (2026-10-13)

### Fixed

- Filtered plugin decks: `/media` and `/decide` honor the `f=` filter (matching items/stats). `mediaSrc` sends the active filter; item lookup uses the filtered snapshot and last served list before reloading `list_items`.
- Plugin item cache stamp includes list generation so a changed filtered list invalidates the 1s item cache (not only folder mtime).
- Deck header: back, title, filter, settings, and menu stay on one row from 320px up; long titles ellipsize instead of wrapping controls.

### Tests

- HTTP regression for filtered plugin media (200) and decide under filter; plugin cache stamp test; CSS regression for top bar nowrap/ellipsis.

## 0.6.2 (2026-10-13)

### Fixed

- Filter flyout panel respects light/dark theme: panel, inputs, combobox listbox, multi-select rows, and footer buttons use shared design tokens (no hard-coded white backgrounds or invisible option text in dark mode).

### Tests

- CSS regression test for filter panel theme tokens; dark-mode Playwright screenshots for combobox and multi-select filters.

## 0.6.1 (2026-10-13)

### Changed

- Filter flyout: single-select filters (`multi: false` or `mode: "single"`) use a searchable combobox (ARIA combobox, keyboard navigation, clear). Multi-select filters always show type-to-search with checkbox rows.

### Fixed

- Plugin item snapshots in `deck_index` are keyed by the active filter (same as `deck_cache.load_items`), so switching filters no longer shows the previous filter’s cards until the TTL expires.
- `load_swipe_plugin_items` no longer substitutes the last good list when `list_items` returns an empty result; fallback is only used after plugin errors.

### Tests

- Node unit tests for filter helper semantics; Playwright combobox + search at 390×844 and 1440×900.
- Regression tests for per-filter snapshots and empty filtered plugin lists.

## 0.6.0 (2026-10-13)

### Added

- **Server Admin** panel (separate from **Manage decks**): network/bind settings, graceful restart with uptime and version, session list with revoke, HTTP compression mode, image transcode-on-serve with disk variant cache and test preview, and hardware-path detection (Pillow CPU, optional ffmpeg/libvips). Owner-only when People mode is on.
- Server settings map to `choice.toml` (`[network]`, `[http]`, `[images]`) and `CHOICE_*` env overrides.

### Tests

- Server settings TOML round-trip, image variant cache keys, admin API owner enforcement.

## 0.5.8 (2026-10-13)

### Fixed

- Plugin filter UI: replace the inline chip strip with a header funnel control and flyout panel (bottom sheet on phones, side drawer on desktop). Selections apply on **Apply** (single buffer flush); active filters show as a one-line summary under the header.

### Tests

- Playwright: 98-option filter deck at 390×844 and 1440×900 — card stays visible and the panel scrolls.

## 0.5.7 (2026-10-12)

### Changed

- Web UI pass: dedicated **Back to decks** control in the header (out of the deck menu), centered layout shell on wide and ultrawide viewports, and a **Settings** panel for per-device preferences (motion, decide-bar labels).
- **Design tokens** (`design-tokens.css`): spacing, radius, colour, type scale, and shadows; `app.css` uses semantic aliases.
- **Icons**: vendored Material Design Icons subset (`mdi.js`, `MDI-ATTRIBUTION.txt`) for header, deck sources, filters, and action buttons (inline SVG, no font/CDN).
- **Server admin** panel for config-backed installs: add/edit/delete decks with confirmations, toolbar on the library, clearer empty states; when People mode is on, only the `owner` in `users.json` (default: first person) may change server config.

### Tests

- Playwright UI review: back button, client settings, server admin, and extra desktop viewports (1440, 1920, ultrawide).

## 0.5.6 (2026-10-12)

### Added

- Deck-declared plugin filters: optional `filters()` schema, `filter=` on `list_items` / `stats`, URL `?f=` (base64url JSON) and per-deck session persistence, chip UI with multi-select, all/any, and sort.
- Optional image codecs: `.heic`, `.heif`, `.jxl` via `pillow-heif` / `pillow-jxl-plugin` extras (`choice.optional_codecs` registers HEIF and JXL openers when installed); folder scan skips zero-byte and unreadable images (cached by mtime and size).

### Tests

- Plugin filter HTTP and selection encoding; image probe cache; legacy plugins ignore unknown `f`.

## 0.5.5 (2026-10-12)

### Fixed

- Wrong-card decides: client reload anchors at response time, merges server items append-only, and falls back to the nearest index when the anchor vanishes (`pile_nav.js`, `app.js`).
- Server honours `held=` on `/items` so ids already on the client stay in order while the source reorders; configurable preload via `[client] buffer`, `CHOICE_CLIENT_BUFFER`, or `--client-buffer`.
- Folder scan already appends new files; undo readmit still pins the card to the front of the index.
- Plugin `handle` may return `ok: true, noop: true`; Choice records the swipe and treats it as success.
- Instant undo: client restores the last card from a short in-memory history (with warmed media blobs), posts undo in the background, and reconciles without jumping away from the restored card. Pending undo pins the card to the pile front to match the server.

### Tests

- Client buffer merge, plugin noop, reorder-with-held regression, pile_nav merge/anchor tests, media ETag/304 cache, instant undo client wiring.

## 0.5.4 (2026-10-12)

### Fixed

- State cleanup: legacy `*.pid.tmp` files younger than 30s are kept without a live-pid probe (the previous branches both probed pid and were equivalent).
- Plugin home index: legacy `list_counts.json` with `total` but no `ids` no longer triggers a synchronous `list_items` on `/api/index`; counts use the saved total while warm runs in the background.
- HTTP `/api/index` with roster enabled now returns the JSON response explicitly.

### Housekeeping

- `.gitignore` ignores local dot-directories while keeping `.github/` and standard build artefacts.
- Package and test folder READMEs; release zip defaults to `dist/choice-<version>.zip`.

### Tests

- State cleanup young-temp and post-probe-age behaviour; cold index HTTP and index_summary without sync list load.
- Skip optional Playwright UI review when Chromium is not installed; steadier perf and work-queue teardown on CI runners.

## 0.5.3 (2026-10-11)

### Fixed

- Atomic writes: unique temp files per write, per-path lock, and state cleanup for mkstemp-style temps (Windows concurrent folder_index saves).
- Windows stale-temp cleanup: `pid_alive` uses `OpenProcess` / `GetExitCodeProcess` instead of `os.kill(pid, 0)`; young temps skip the probe.
- Plugin home counts: serve persisted `list_counts.json` immediately, refresh in the background when older than ~60s (startup + index), one refresh per deck at a time.
- Home UI: very long unbroken deck titles wrap without pushing the ⋯ menu off-screen; count meta no longer duplicates “N left” when the label already includes it.
- Playwright home-stress pins `/api/index` so desktop runs are not overwritten by live index data.

### Tests

- Concurrent atomic JSON writes; Windows `pid_alive` mock on Linux; background stale count refresh; UI review route stub and count-meta checks.

## 0.5.2 (2026-10-10)

### Fixed

- Home deck list: titles no longer break mid-word; long count labels sit on a muted second line on phones (ellipsis + `title` tooltip), with side-by-side layout on wider screens.
- Deck header count truncates on narrow viewports; menu icon meets 44px tap target.
- Wider library column on large laptops (920px).

### Tests

- Playwright UI review at six viewport sizes with stress fixtures, overflow/title/tap-target assertions, and 390px + 1366px screenshots.

## 0.5.1 (2026-10-10)

### Fixed

- `[images]` extra: `Pillow>=10` with no upper pin (compatible with Pillow 12.x in production).
- Plugin `count_label` no longer forces endless mode; `endless: false` keeps normal totals and shows the label beside the remaining count.
- Swipe `deck.py` modules with `stats()` pass `endless` and `count_label` through like native plugins (`ursala_swipe` source alias included).

### Tests

- Labeled-not-endless plugin fixture; swipe stats passthrough fixture.

## 0.5.0 (2026-10-10)

### Packaging (phase 1)

- PyPI distribution name **`choice-swipe`**; import package and console command remain **`choice`**.
- Wheel ships `choice/web/*` only (no tests, docs, or examples in the wheel).
- Optional extra **`images`**: `Pillow>=10,<12`.
- Config fields overridable via **`CHOICE_*`** env vars (documented in `choice.example.toml`).
- GitHub Actions: **CI** on push/PR; **release** on `v*` tags (matrix 3.11–3.13, Linux + Windows), sdist/wheel + SHA256SUMS, PyPI publish gated on repo variable `PYPI_PUBLISH`.

### Fixed

- Startup removes stale `*.<pid>.tmp` atomic-write temps from state dirs (dead pid or older than ~10 minutes).
- Action icons: **Equal** uses equals; labels like **A is me** / **B is me** use letter icons.

### Tests

- State tmp cleanup, config env override, wheel contents audit.

## 0.4.17 (2026-10-10)

### Fixed

- Plugin item conversion no longer checkpoints `list_counts.json` every five rows; counts persist once per successful plugin load via temp file, fsync, and atomic replace.
- All state JSON writes (`list_counts.json`, folder index, work queue, count/view prefs, users roster, folder stats) use the same atomic helper.
- `Equal` uses the equals icon; single-letter **A** / **B** left/right labels use letter icons (spicy_elo, spicy_faces).

### Tests

- Regression: at most one `list_counts.json` write per load and concurrent readers never see invalid JSON.
- Performance: 8k-item plugin first load stays under 300 ms Choice overhead.

## 0.4.16 (2026-10-10)

### Fixed

- Action bar icons: whole-word label matching with negatives before positives (`Dislike` no longer shows ✓).
- Ambiguous pairs (A/B, Keep/Merge, Like/Super-like), neutral labels, trash vs delete-to-_trash, and direction defaults when icons would collide.
- Arrow and undo SVG paths.
- Unknown `icon` in deck config logs a warning and falls back instead of breaking the deck; `sort_*_icon` alone no longer adds a direction button.
- Plugin `list_items` during home/items load: exceptions and bad rows are caught, partial lists are recorded, and the last good snapshot is served when a refresh fails.

### Tests

- Node table tests for label→icon mapping and arrow direction vectors.
- Config side-effect tests and a chaotic plugin fixture for partial/failed loads.

## 0.4.15 (2026-10-10)

### Changed

- Deck action bar: left and right swipes pin to the edges; up, down, extra buttons, and undo sit in the centre.
- Narrow screens show inline SVG icons (with full labels as `aria-label`); wider screens show icon plus text when it fits, otherwise icon only. Labels never hyphenate or break mid-word.
- Per-deck icon overrides via `sort_right_icon`, `directions.up.icon`, or `icon` on a direction in `deck.json`.

### Tests

- Playwright action bar layout at 360, 390, and 768px; config icon overrides.

## 0.4.14 (2026-10-10)

### Added

- Plugin `stats()` may set `endless: true` and/or `count_label` so buffer-sized piles show ∞ or a custom label on home and in the deck header; `auto` count mode hides the meter. `/api/index` and `/items` expose `endless` and `count_label`.

### Fixed

- Cold plugin `/items` no longer forces a full `list_items()` during home `index_summary`; the first page waits on the plugin list only (measured overhead is small vs plugin work such as spicy_elo’s own load).

### Tests

- Endless stats (label only, endless only, and neither). Cold `/items` timing vs a slow `list_items` fixture.

## 0.4.13 (2026-10-10)

### Added

- Optional top-level `title` in `choice.toml` and `--title` / `CHOICE_TITLE` set the browser tab, header, and PWA manifest name (default remains Choice).
- Web app manifest and a scoped service worker under each instance `--base-path` so Sky and Spicy can share one host without clashing.

### Tests

- Config title loading, CLI override, and HTTP checks for manifest, service worker, and scoped routes.

## 0.4.12 (2026-10-10)

### Fixed

- Order and filter dialog stacks each label above its field at full width on phones, with thumb-sized inputs and a reshuffle control for the random seed (empty means auto, not the deck id).

### Tests

- Layout checks for stacked order/filter fields; Playwright accepts `CHOICE_TEST_BASE_URL` instead of assuming a fixed dev port.

## 0.4.11 (2026-10-10)

### Fixed

- Modal shell uses an explicit width (`min(100vw - 24px, 480px)`) so Android Chrome no longer leaves order/filter and other dialogs tiny in the top-left corner.
- Add/edit deck setup runs inside the shared `ChoiceDialog` instead of inline in `main`.

### Tests

- Playwright modal layout on phone viewports (360×640, 390×844, 412×915) with mobile UA and `deviceScaleFactor` 2.6; asserts width, placement, and control clicks for every registered modal trigger.

## 0.4.10 (2026-10-09)

### Fixed

- Swipe source: `directions` in deck options no longer crash startup (`_config_directions` vs plugin parser name clash).
- A deck that fails to open becomes an error row; other decks still load (exceptions are logged).

## 0.4.9 (2026-10-09)

### Fixed

- Plugin `/items` offset paging no longer slices twice (page 2+ empty while `left` still showed cards).
- Plugin home counts refresh from the live list on cold read (including with warm-up disabled); totals stay numeric after hot reload.
- Sort decks honour `sort_<dir>_label` and labelled sort targets in the API and swipe UI.
- Single-image cards: photo fills the frame with `object-fit: contain`, caption sits below without overlapping or a blurred top band; duplicate title under the image removed.
- Linux tests wait on work-queue and move readiness instead of fixed sleeps; release zip test skips outside a git checkout.

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
