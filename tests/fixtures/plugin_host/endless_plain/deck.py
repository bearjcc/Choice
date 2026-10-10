"""Endless plugin deck (stats only, no custom label)."""


class Deck:
    id = "endless_plain"
    title = "Endless plain"
    directions = {"right": {"label": "Yes"}}

    def list_items(self, filter=None):
        return [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}]

    def stats(self):
        return {"endless": True}

    def handle(self, item_id, direction, note=None):
        return {"ok": True}
