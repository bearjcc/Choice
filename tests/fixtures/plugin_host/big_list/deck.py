"""Many-item plugin deck for offset paging tests."""


class Deck:
    id = "big_list"
    title = "Big list"
    directions = {"right": {"label": "Yes"}}

    def list_items(self, filter=None):
        return [{"id": f"item-{i:04d}", "title": f"Card {i}"} for i in range(500)]

    def handle(self, item_id, direction, note=None):
        return {"ok": True}
