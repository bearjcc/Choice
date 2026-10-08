"""Counts how many times the plugin class is constructed."""

import os

PATH = os.environ.get("INSTANCE_COUNTER_PATH", "")


class Deck:
    id = "instance_counter"
    title = "Instance counter"
    directions = {"right": {"label": "Yes"}}

    def __init__(self):
        if PATH:
            try:
                n = int(open(PATH, encoding="utf-8").read().strip() or "0")
            except OSError:
                n = 0
            with open(PATH, "w", encoding="utf-8") as handle:
                handle.write(str(n + 1))

    def list_items(self, filter=None):
        return [{"id": "one", "title": "One"}]

    def handle(self, item_id, direction, note=None):
        return {"ok": True}
