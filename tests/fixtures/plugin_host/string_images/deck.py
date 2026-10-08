from pathlib import Path

HERE = Path(__file__).resolve().parent


class Deck:
    id = "string_images"
    title = "String images"
    directions = {"right": {"label": "Yes"}}

    def list_items(self, filter=None):
        return [
            {
                "id": "listing",
                "title": "Listing",
                "images": ["good.png", "missing.png", 99],
            }
        ]

    def handle(self, item_id, direction, note=None):
        return {"ok": True}
