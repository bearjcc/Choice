"""~8k items for list_counts write and load overhead tests."""

_COUNT = 8300


class Deck:
    id = "big_list_8k"
    title = "Big list 8k"
    directions = {"right": {"label": "Yes"}}

    def list_items(self, filter=None):
        return [{"id": f"item-{i:05d}", "title": f"Card {i}"} for i in range(_COUNT)]

    def handle(self, item_id, direction, note=None):
        return {"ok": True}
