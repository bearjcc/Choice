class Deck:
    id = "decided_flag"
    title = "Decided flag"
    directions = {"right": {"label": "Yes"}}

    def list_items(self, filter=None):
        return [
            {"id": "open", "title": "Open"},
            {"id": "done", "title": "Done elsewhere", "decided": True},
        ]

    def handle(self, item_id, direction, note=None):
        return {"ok": True}
