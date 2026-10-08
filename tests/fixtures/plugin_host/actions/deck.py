"""Plugin custom action."""

import os

PATH = os.environ.get("ACTION_COUNTER_PATH", "")


class Deck:
    id = "actions"
    title = "Actions"
    directions = {"right": {"label": "Yes"}}
    actions = [{"id": "load_more", "label": "Load 100 more", "confirm": True}]

    def list_items(self, filter=None):
        return [{"id": "only", "title": "Only"}]

    def handle(self, item_id, direction, note=None):
        return {"ok": True}

    def run_action(self, action_id):
        if action_id != "load_more":
            return {"ok": False, "message": "unknown"}
        if PATH:
            try:
                n = int(open(PATH, encoding="utf-8").read().strip() or "0")
            except OSError:
                n = 0
            with open(PATH, "w", encoding="utf-8") as handle:
                handle.write(str(n + 1))
        return {"ok": True, "message": "Loaded"}
