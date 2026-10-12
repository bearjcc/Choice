"""Plugin that reverses list order on every list_items call (simulates live reorder)."""


class Deck:
    id = "reorder_list"
    title = "Reorder list"
    directions = {"right": {"label": "Yes"}}

    def __init__(self):
        self._flip = False

    def list_items(self, filter=None):
        self._flip = not self._flip
        rows = [
            {"id": "card-a", "title": "A"},
            {"id": "card-b", "title": "B"},
            {"id": "card-c", "title": "C"},
        ]
        if self._flip:
            rows.reverse()
        return rows

    def handle(self, item_id, direction, note=None):
        return {"ok": True, "noop": True}
