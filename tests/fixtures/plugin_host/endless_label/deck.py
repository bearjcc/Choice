"""Endless plugin deck with a custom count label."""


class Deck:
    id = "endless_label"
    title = "Endless label"
    directions = {"right": {"label": "Yes"}}

    def list_items(self, filter=None):
        return [{"id": "a", "title": "A"}]

    def stats(self):
        return {"endless": True, "count_label": "∞ · 62% unsettled"}

    def handle(self, item_id, direction, note=None):
        return {"ok": True}
