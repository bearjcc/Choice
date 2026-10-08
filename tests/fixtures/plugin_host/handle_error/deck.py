class Deck:
    id = "handle_error"
    title = "Handle error"
    directions = {"right": {"label": "Yes"}}

    def list_items(self, filter=None):
        return [{"id": "x", "title": "X"}]

    def handle(self, item_id, direction, note=None):
        raise RuntimeError("plugin says no")
