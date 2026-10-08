from pathlib import Path

HERE = Path(__file__).resolve().parent


class Deck:
    id = "gallery"
    title = "Gallery"
    directions = {"right": {"label": "Yes"}}

    def list_items(self, filter=None):
        a = HERE / "a.png"
        b = HERE / "b.png"
        return [
            {
                "id": "listing",
                "kind": "profile",
                "title": "Listing",
                "body": "Two photos",
                "images": [
                    {"path": str(a), "caption": "Front"},
                    {"path": str(b), "caption": "Kitchen"},
                ],
            }
        ]

    def handle(self, item_id, direction, note=None):
        return {"ok": True}
