# SPDX-License-Identifier: AGPL-3.0-only
"""Copy each swipe into labels.jsonl.

Choice already writes .choice/decisions.jsonl. This hook is the extra
step the older Python decks did by hand: append a label somewhere else.

It is not wired up. To turn it on, add this to deck.json:

  "hook": { "command": ["python", "hook.py"] }

A required hook (the swipe is discarded if this exits non-zero):

  "hook": { "command": ["python", "hook.py"], "required": true }

The process gets one JSON object on stdin and no shell.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

body = json.load(sys.stdin)
line = {
    "id": body.get("item"),
    "label": "clear" if body.get("action") == "undo" else body.get("value"),
    "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
}
path = Path(__file__).resolve().parent / "labels.jsonl"
with path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(line, ensure_ascii=False) + "\n")
