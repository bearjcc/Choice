import os


class Deck:
    id = "media_absolute"
    title = "Absolute path"
    directions = {"right": {"label": "Yes"}}

    def list_items(self, filter=None):
        path = os.environ.get("MEDIA_ABSOLUTE_PATH", "")
        return [{"id": "cached", "title": "Cached", "kind": "image", "image_path": path}]

    def handle(self, item_id, direction, note=None):
        return {"ok": True}
