"""Plugin that throws mid-list or mutates while iterating."""


class Deck:
    id = "chaotic_list"
    title = "Chaotic list"
    directions = {"right": {"label": "Yes"}}

    def list_items(self, filter=None):
        mode = getattr(self, "_mode", "partial")
        if mode == "raise":
            raise RuntimeError("list_items exploded")
        if mode == "throw":
            return [
                {"id": "good-1", "title": "First"},
                {"id": "good-2", "title": "Second"},
                bad,
            ]
        if mode == "mutate":
            items = [
                {"id": "m-1", "title": "One"},
                {"id": "m-2", "title": "Two"},
            ]
            items.append({"id": "m-3", "title": "Three"})
            return items
        return [{"id": "solo", "title": "Only"}]

    def handle(self, item_id, direction, note=None):
        return {"ok": True}


bad = object()
