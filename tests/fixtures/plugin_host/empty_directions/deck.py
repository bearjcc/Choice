"""Plugin with empty directions object."""


class Deck:
    id = "empty_directions"
    title = "Empty directions"
    directions = {}

    def list_items(self, filter=None):
        return [{"id": "a", "title": "A"}]

    def handle(self, item_id, direction, note=None):
        return {"ok": True}
