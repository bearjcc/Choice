# Choice

Swipe through a pile and decide. Photos, files, a true or false quiz, a round robin, a knockout, a branching story, "which of these two". The pile stays on the computer that has the files. A phone is just a browser pointed at that computer.

Choice is the generic shape of a private swipe tool: four directions, extra buttons, undo, and a log. The common piles are a `deck.json`. The strange ones (call an API, rebuild a dataset) are a small hook.

## Two minutes

From this folder:

```
python -m choice examples
```

Open the address it prints. Arrows decide. U undoes. I opens the card.

## Config and sources (0.2)

For several decks and remote piles, use a config file:

```
cp choice.example.toml choice.toml
python -m choice --config choice.toml
```

Sources can be local folders (`type = "images"` for photo piles), Swipe `deck.py` plugins, Immich 3.x, RSS, or WebDAV. State, decisions, and media cache live under `[state] dir` in the config (see `choice.example.toml`), not inside the source. See [DECKS.md](DECKS.md) for every field, including `sort_right`, `sort_left`, `sort_up`, and `sort_down`.

With the UI running in config mode, open **Sources and decks** on the library page to add a folder deck, set sort targets, and test a connection.

## Point it at your own photos

```
python -m choice D:\camera\dump
```

By default this is **results** mode: swipes are logged and files stay put. Add a `deck.json` with `"output": "sort"` and sort folders if you want copyparty-style sorting. The `examples/photos` deck still moves trashes explicitly via directions.

Decisions are appended to `.choice\decisions.jsonl` (or the config state dir). Latest line per card wins. Undo adds a line; it does not rewrite history.

## Your own labels

Copy `examples\yes-no` and edit `deck.json`. The whole format is [DECKS.md](DECKS.md). A folder of decks (each child has a `deck.json` or an `items.jsonl`) becomes the list on the front page. The other folders are a quiz with a score, a round robin, a knockout, and a short branching story.

```
python -m choice --tally examples\yes-no
```

## Phone

The server listens on this computer only, until you ask otherwise.

```
python -m choice --lan D:\camera\dump
```

`--lan` means anyone who can reach that port can label cards and move files. Use it on a network you trust, or put Tailscale (or an SSH tunnel) in front and keep the bind on `127.0.0.1`. A name is not a password.

## People

Optional. Leave it off and there is one shared log, and every deck is listed.

People, on the page, adds a name and ticks which decks that person sees. Each person has their own swipes. The browser remembers who you picked. The file, if you would rather edit it, is `.choice/users.json`. The format is in [DECKS.md](DECKS.md).

## Read the code

| File | What it is |
| --- | --- |
| `choice/load.py` | Find a deck and turn it into cards |
| `choice/act.py` | Write the decision, move a file, undo |
| `choice/httpd.py` | The local site |
| `choice/media.py` | Phone-sized `/media` cache (optional Pillow via `choice[images]`) |
| `choice/cli.py` | The command |
| `choice/people.py` | Optional names, and which decks each one sees |
| `choice/web/` | The page: `index.html`, `app.js`, `app.css` |

No packages are required. Python 3.11 or newer. Pillow is optional (`pip install 'choice[images]'`) for WebP/JPEG copies around 1600px. Without it, `/media` sends the original file. Use `?full=1` on a media URL for the original when Pillow is installed.

```
python -m unittest discover -s tests
python -m ruff check choice tests
```

## Licence

Choice is free software under the GNU Affero General Public License, version 3. You can run it and change it. If you modify it and let other people use that version over a network, those people must be able to get the source. The running site serves the licence at `/license`. See `LICENSE`.
