"""Plugin with invalid directions shape."""


class Deck:
    id = "malformed_directions"
    title = "Malformed directions"
    directions = ["left", "right"]

    def list_items(self, filter=None):
        return [{"id": "x", "title": "X"}]

    def handle(self, item_id, direction, note=None):
        return {"ok": True}
