"""Appends one JSON line per handle/undo for exactly-once tests."""

import json
import os

PATH = os.environ.get("LABEL_ONCE_PATH", "")


class Deck:
    id = "label_once"
    title = "Label once"
    directions = {
        "right": {"label": "Yes"},
        "left": {"label": "No"},
    }

    def list_items(self, filter=None):
        return [{"id": "only", "title": "Only card"}]

    def handle(self, item_id, direction, note=None):
        if PATH:
            with open(PATH, "a", encoding="utf-8") as handle:
                handle.write(json.dumps({"item": item_id, "direction": direction}) + "\n")
        return {"ok": True, "undo_token": {"step": "handle"}}

    def undo(self, item_id, undo_token):
        if PATH:
            with open(PATH, "a", encoding="utf-8") as handle:
                handle.write(json.dumps({"item": item_id, "undo": True}) + "\n")
        return {"ok": True}
