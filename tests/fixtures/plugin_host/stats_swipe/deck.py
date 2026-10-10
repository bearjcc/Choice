"""Swipe fixture: stats() on deck module (passthrough smoke test)."""


class Deck:
    id = "stats_swipe"
    title = "Stats swipe"
    directions = {"right": {"label": "Yes"}}

    def list_items(self, filter=None):
        return [{"id": "x", "title": "X"}]

    def stats(self):
        return {"endless": True, "count_label": "from stats()"}

    def handle(self, item_id, direction, note=None):
        return {"ok": True}
