# Decks

A deck is a pile of cards and a set of named swipes. You can write one as a folder, or point Choice at a folder or a file and accept the defaults.

`python -m choice --help` starts the server. This file is the format.

## The smallest deck

`examples/yes-no`:

```json
{
  "title": "Yes or no",
  "source": { "type": "jsonl", "path": "items.jsonl" },
  "show": { "title": "{{n}}", "body": "{{q}}", "chips": ["topic"] },
  "directions": {
    "right": { "label": "Yes", "value": "yes" },
    "left": { "label": "No", "value": "no" },
    "down": { "label": "Skip", "value": "skip", "later": true }
  }
}
```

`{{q}}` is replaced with that field from the row. Anything Choice does not recognise is ignored and named in a warning on the page, so a typo is visible.

## What you can point at

Choice looks at the path you gave it, in this order:

1. A file named `deck.json`, or a `.jsonl`, `.csv`, or `.json` file, is one deck. If the file sits in a folder that already has `deck.json`, that folder wins.
2. A folder with `deck.json` is that deck.
3. A folder whose children have `deck.json` or `items.jsonl` / `items.csv` / `items.json` is a library. The front page lists them. A loose photo next to those children is not its own deck: put it in a child folder, or point Choice at that folder directly.
4. A folder of files, pointed at directly, is one deck. Images preview. Other files show their name and size. Left moves them to `.choice/trash`.

Dot-folders, including `.choice`, are never cards. `deck.json` is never a card. Symlinks are skipped. Listing is the top of the folder only, unless the source says `"recursive": true`.

A `.csv` needs a header row. A `.json` file is a list of objects, or `{"items": [ ... ]}`. A `.jsonl` file is one object per line. Blank lines are skipped. A broken line is skipped and reported. Choice reads the whole file each time, so new rows show up on reload. It is a review pile, not a database.

Rows need a stable `id`. If you omit it, Choice uses the row number, which changes when you insert a line at the top.

## Directions

`left`, `right`, `up`, `down`. Each one:

| Key | Meaning |
| --- | --- |
| `label` | Text on the button |
| `value` | What is written in the log. Defaults to a slug of the label |
| `later` | `true` means the card stays in "still to do" (a skip). Default `false` |
| `does` | `label` (default), `move`, or `copy` |
| `into` | Folder, inside the deck, for `move` and `copy`. Default `.choice/out/<value>` |
| `color` | Optional `#rgb` or `#rrggbb`. Anything else is ignored |

On a phone, left and right are a drag. Up and down are buttons, because a vertical drag is how the card scrolls.

If you leave `directions` out, rows get Yes, No, and Skip. A folder of files gets Keep, Trash, Favourite, and Skip.

`buttons` is a list of extra actions, same fields plus an `id`. The ids `left`, `right`, `up`, `down`, `undo`, and `note` are reserved.

```json
"buttons": [{ "id": "flag", "label": "Flag", "value": "flag" }]
```

## What a swipe does

`label` only writes the log.

`move` renames the file into `into`, keeping its relative path (`a/b.png` lands at `into/a/b.png`). If that path already exists, the swipe is refused and nothing is written. Undo moves it back. Choice will not move a file that lives outside the deck folder.

`copy` copies the file. Undo removes that copy, and only that copy.

Choice never deletes a source file. Emptying `.choice/trash` is something you do yourself, later, when you mean it.

## What the card shows

`show.title` and `show.body` are templates. `show.chips` is a list of field names, drawn on the card. An empty list draws none. If you leave `chips` out, Choice guesses up to six fields. `show.reveal` is a list of field names shown only in Details, which is where an answer key belongs. `show.image` names the field that holds an image path (relative to the deck, or absolute). If you omit it, Choice looks at `image` or `image_path`. One picture per card. A list uses the first entry.

`blind: true` starts the deck with title, chips, and reveal hidden. The body stays, so put the text the reviewer must see in `body`. The Blind button remembers your choice in the browser. File cards still show the file name, because otherwise there is nothing to judge.

`show.pair` is an A/B card. It has two sides, `a` and `b`. Left still chooses `a`. Right still chooses `b`. On a narrow window, `a` sits above `b`. On a wide window (a desktop, or a tablet on its side) the two sides sit next to each other. That is the useful layout for a writing test, and for two pictures, especially portraits: a single portrait wastes the width, and two of them fill it.

A side is a template string, or an object with `body` and `image`. `image` is a field name, the same idea as `show.image`. Omit `label` and the pane uses the left or right button label.

On a pair card, Blind still hides chips and reveal. The title stays, because it is the question both sides are answering.

```json
"show": {
  "title": "{{context}}",
  "pair": { "a": "{{A}}", "b": "{{B}}" },
  "reveal": ["real"]
}
```

```json
"pair": {
  "a": { "image": "before" },
  "b": { "image": "after" }
}
```

Without `show`, Choice guesses: a title from `title`, `name`, `question`, `q`, or `prompt`, and a body from `body`, `text`, `content`, or `detail`.

## Score

`score.field` names a field on each row. Choice compares it with the swipe value, ignoring capital letters and spaces at the ends. Each match is one point. A skip (`later`) is not a point, and it does not finish the quiz.

The points show when every row that has an answer has been decided. Until then, Counts is only how many times you swiped each way.

`examples/true-false` is eight statements. Right is True, left is False. Blind is on, so the answer stays in Details. The score at the end lists them anyway.

## Contest

`contest` builds the cards from the rows. The rows are the names, not the cards. `contest.name` is the field to show. The default is `name`. Left picks the first name, right picks the second. The log records that name's id.

`contest.kind` is `robin` or `bracket`.

A contest needs a left and a right swipe, and neither of them can be `later`. The examples paint both buttons the same colour, because neither side is a yes or a no.

### robin

Every pair meets once. A win is one point. When every pair has been played, the names are ordered by wins. If two names have the same number of wins, the one that beat the other ranks higher. If a group is still tied, those names play a playoff. The playoff does not change the win totals. It only orders the tie: the winner of a playoff match ranks above the loser, and that continues until the order is complete. If a playoff round has an odd name, the first of those names waits.

`examples/round-robin` is five bakeries. That is ten matches, plus a playoff only if some of them tie.

### bracket

Lose and you are out. Win and you go on. The list order is the bracket: the first row plays the second, the third plays the fourth, and so on. If one name has no opponent, the first name still in waits for the next round.

Four matches in a round is a quarter-final, two is a semi-final, and one (with nobody waiting) is the final. The result places everyone. The winner is first, the other finalist is second, and anyone who lost in the same round shares the next place.

`examples/knockout` is eight shelters, so the first round is a quarter-final.

## Story

`story` is a branching pile. Each row is a scene. You only see the scene you are on.

```json
"story": {
  "start": "road",
  "left": "lid",
  "right": "rid",
  "labels": { "left": "l", "right": "r" }
}
```

`left` and `right` name the fields that hold the next card's id. `labels` names the fields that hold the button text. `start` is the first card. If you omit it, the first row is the start.

A scene with no next id is an ending. The page shows that text when you arrive, and it is not a swipe. Any other direction has to be `later`, because it does not turn the page. Undo is how you step back.

`examples/pigs` is a short telling of the three little pigs. Neither swipe is the correct one.

## People

Optional. No `users.json` means one shared log, and the front page lists every deck.

The file is `.choice/users.json` next to the folder or file you pointed Choice at. In a library that is the library folder, not each deck.

```json
{
  "users": [
    {"id": "ada", "name": "Ada", "decks": ["yes-no", "photos"]},
    {"id": "bea", "name": "Bea", "decks": "*"}
  ]
}
```

`id` is lowercase letters, digits, `_`, and `-`. Omit it and Choice slugs the name. `decks` lists deck ids (the folder names). `"*"` means every deck, including ones you add later. An empty list means that person sees none.

On the page, People adds a name and Assign ticks decks. Ticking every deck that exists now is stored as `"*"`. The browser remembers who you picked. A name is not a password: anyone who can open the page can pick a name or change who sees what.

Each person has their own log at `.choice/users/<id>/decisions.jsonl` inside that deck. Swipes from before the file existed stay in the shared log. Choice does not copy them. A swipe that moves or copies a file still changes that one file, so the other person's pile changes too.

Remove the last person, or delete `users.json`, and Choice uses the shared log again. Logs already written stay on disk.

## The log

`.choice/decisions.jsonl` next to the deck. With People on, that path is `.choice/users/<id>/decisions.jsonl` instead. One JSON object per line:

```json
{"type": "decision", "id": "…", "item": "1", "direction": "right", "value": "yes", "label": "Yes", "later": false, "note": "", "ts": "…", "file": null}
```

A move also stores `file_op` with `from` and `to`. An undo is:

```json
{"type": "undo", "ref": "…", "item": "1", "ts": "…"}
```

The latest decision for an item that has not been undone is the one that counts. Undo targets the latest swipe in the whole deck, not "this card". A note (Details, or the note field) is stored with the next swipe and then cleared. 500 characters.

A file you pointed at directly, rather than a folder, keeps its log in `.choice/<file-slug>/` so two files in one folder do not share a log.

## Hooks

A hook is a program, not a shell string. Choice runs it with the deck folder as the working directory, and writes one JSON object to stdin:

```json
{"action": "decide", "deck": "which-one", "item": "pair-1", "direction": "left", "value": "A", "label": "A", "note": "", "file": null, "fields": {}, "decision_id": "…"}
```

`action` is `decide` or `undo`. `fields` is the row, with nested objects left out. `user` is the person id, or `""` when People is off.

```json
"hook": { "command": ["python", "hook.py"], "timeout_seconds": 20 }
```

Exit 0. On failure, Choice still keeps the swipe and says the hook failed.

`"required": true` flips that. The hook must succeed or the swipe is discarded. A file move is reversed if the hook then fails. Use this when the hook is the real effect (append a label file, call an API) and the log alone is not enough. `examples/which-one/hook.py` is a label file you can turn on. `examples/immich/hook.py` bins or favourites an Immich asset. The card id is the asset id. Neither hook is wired up.

`timeout_seconds` is 1 to 120. Default 20.

## Phone and photos

Bind stays on this computer unless you pass `--lan` or `--host`. See the README.

HEIC is not previewed. The decision still applies to the file. If Pillow is installed, JPEG, PNG, WebP, and BMP are shrunk to 1600px and cached in `.choice/cache`. Delete that folder whenever you like.

A pair of images uses that same preview, once per side. On a wide window the two pictures sit next to each other.

## Keys

Arrow keys match the directions. On an A/B card, A and B pick the left and right side; on a wide screen you can click a side. U undoes. I opens Details. Blind, Counts, and Show all sit above the card.

## Config and deck sources (0.2)

Choice can run from a config file instead of a single folder:

```
python -m choice --config choice.toml
```

Set `CHOICE_CONFIG` to the same path if you prefer. Copy `choice.example.toml` to `choice.toml` (gitignored). Secrets are **env var names** in the config, never values. Optional `state.secrets_file` (default `.choice-secrets` next to the config) holds `NAME=value` lines; the add-deck UI writes there when you paste a key.

Per-deck state (decisions, ratings) lives under `state.dir/<deck-id>/`, not inside the source. Read-only sources (RSS, remote APIs) work because nothing is written back to them.

### Source types

| Type | Role | Media | Destructive actions |
| --- | --- | --- | --- |
| `folder` | Local `deck.json`, items files, or a file pile | Files on disk | Sort mode moves files (see below) |
| `swipe` | Swipe `deck.py` plugin folders unchanged | `image_path`, `media_bytes` hook | Plugin `handle` / `undo` |
| `immich` | Album or search feed (`mount` = `album:<id>` or `search:`) | Streamed preview | Left swipe trashes in Immich (undo restores) |
| `rss` / `atom` | Feed URL in source `url` | Usually none | None (log only) |
| `webdav` | Image files over WebDAV | Fetched per card | None (log only) |

`GET /api/source-types` lists types. `POST /api/sources/test` with a source object and `mount` previews items. `GET /api/config` returns sources and decks with secrets masked (`***`).

### Folder source fields

On a `folder` source or in `deck.json` `source`:

| Field | Default | Meaning |
| --- | --- | --- |
| `output` / `output_mode` | `results` | `results`: log only, files stay put. `sort`: each direction can move into a subfolder |
| `recursive` | `false` | When true, scan subfolders |
| `include` / `include_globs` | (all) | Glob list; match file name or relative path |
| `exclude` / `exclude_globs` | (none) | Glob list; excluded paths are skipped |
| `sort` / `sort_targets` | (none) | Map direction id → folder name, e.g. `{ "right": "keep", "left": "delete" }` |
| `sort_right`, `sort_left`, … | (none) | Shorthand per direction in `choice.toml` |

In **sort** mode, files already sitting inside a sort target folder are never listed, even when `recursive` is true. In **results** mode, decided cards drop off the pending pile (same as other decks).

Moves use safe rename on collision (`name_1.ext`), same-volume move or copy-verify-delete across volumes, and `file_op` lines in the log for undo.

### Swipe plugins

Point a `swipe` source at the parent of plugin folders (a directory of `deck.py` plugin folders). Each `[[decks]]` row sets `mount` to the folder name. Choice keeps one plugin instance per deck and reloads `deck.py` only when its file changes. On reload it calls `close`, `shutdown`, or `stop` on the old instance when present. It calls `list_items`, `handle`, `undo`, optional `media_bytes`, `stats`, and `run_action`. State stays in Choice's `state.dir`.

The home page does not call `list_items` for plugin decks until you open that deck (counts use a short-lived snapshot). `list_items` for one deck never runs concurrently.

`media_bytes` receives the full item dict from `list_items` (same as Swipe). Optional query `n` selects an image index when the hook accepts `n`. A hook that only accepts an item id string still works.

Rows may set `"decided": true` so Choice treats them as finished: hidden from the pending pile and counted as decided.

Profile cards may set `"kind": "profile"` or an `images` list. Each entry is either a path string or an object with `path` / `file` and optional `caption`. Relative paths must stay inside the plugin folder; absolute paths may point anywhere on disk (plugins are trusted code). Tokens such as `immich:<id>` are fine when the plugin implements `media_bytes`. The first resolved image is the card's main photo when `image_path` is omitted. Bad relative paths are reported in deck warnings. The UI shows a tappable photo strip that does not steal the card's left/right swipe.

Plugin `actions` is a list of `{"id", "label", "confirm"?}`. The phone menu posts to `/api/decks/<id>/action` with `{"action": "<id>"}`.

Per-deck options in `choice.toml` (under `[[decks]]`):

| Option | Meaning |
| --- | --- |
| `private = true` | Omit from `GET /api/feed` summaries (integrations and future notification feeds). The deck still appears on the main index. |
| `notify = false` | Same as `private = true`. |

When a plugin `handle` raises or returns `ok: false`, the swipe is not written to the log and the page shows the plugin message (trimmed, HTML-escaped).

### Contest modes: taste and rated

`contest.kind` can be `robin`, `bracket`, `taste`, or `rated`.

- **taste**: stage 1 is yes/no (or like/dislike) on every row. Stage 2 ranks the likes: bracket or robin for small sets, rated pairs for larger sets.
- **rated**: Glicko-style ratings; each card is a pairwise A/B match. The count label shows confidence (e.g. `Rated 42%`). Export via `GET /api/decks/<id>/export` includes `decisions` and any `ranking` report.

Examples: `examples/taste`, `examples/rated`.
