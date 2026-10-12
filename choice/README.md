# choice package

Python package for the Choice local server and CLI (`python -m choice`).

| Area | Module |
| --- | --- |
| Deck loading | `load.py`, `open.py`, `open_cache.py` |
| Swipes and undo | `act.py`, `flow.py`, `work_queue.py` |
| HTTP API and static UI | `httpd.py`, `web/` |
| Folder piles | `folder_index.py`, `folder_deck.py` |
| Swipe plugins | `swipe_plugin.py`, `plugin_items.py`, `deck_index.py` |
| Config and people | `config.py`, `people.py` |
| Sources (Immich, RSS, WebDAV, …) | `sources/` |

Deck and plugin authoring is documented in the repo root [DECKS.md](../DECKS.md).
