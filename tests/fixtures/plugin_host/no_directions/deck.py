"""Plugin with no directions attribute (like some legacy swipe decks)."""


class Deck:
    id = "no_directions"
    title = "No directions"

    def list_items(self, filter=None):
        return [{"id": "one", "title": "Card one", "body": "Still decidable"}]

    def handle(self, item_id, direction, note=None):
        return {"ok": True}
