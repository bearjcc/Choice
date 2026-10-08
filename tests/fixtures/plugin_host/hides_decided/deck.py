class Deck:
    id = "hides_decided"
    title = "Hides decided"
    directions = {"right": {"label": "Keep"}}

    def list_items(self, filter=None):
        return [
            {"id": "open-1", "title": "One"},
            {"id": "open-2", "title": "Two"},
            {"id": "open-3", "title": "Three"},
        ]

    def handle(self, item_id, direction, note=None):
        return {"ok": True}
