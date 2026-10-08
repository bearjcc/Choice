"""Counts list_items calls."""

import os

PATH = os.environ.get("LIST_COUNTER_PATH", "")


class Deck:
    id = "list_counter"
    title = "List counter"
    directions = {"right": {"label": "Yes"}}

    def list_items(self, filter=None):
        if PATH:
            try:
                n = int(open(PATH, encoding="utf-8").read().strip() or "0")
            except OSError:
                n = 0
            with open(PATH, "w", encoding="utf-8") as handle:
                handle.write(str(n + 1))
        return [{"id": "a", "title": "A"}]

    def handle(self, item_id, direction, note=None):
        return {"ok": True}
