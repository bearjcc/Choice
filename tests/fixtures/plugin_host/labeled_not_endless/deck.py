"""Plugin with count_label but explicit endless: false."""


class Deck:
    id = "labeled_not_endless"
    title = "Labeled not endless"
    directions = {"right": {"label": "Yes"}}

    def list_items(self, filter=None):
        return [
            {"id": "a", "title": "A"},
            {"id": "b", "title": "B"},
            {"id": "c", "title": "C"},
        ]

    def stats(self):
        return {"endless": False, "count_label": "2 borderline left"}

    def handle(self, item_id, direction, note=None):
        return {"ok": True}
