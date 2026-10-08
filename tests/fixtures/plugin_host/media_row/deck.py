"""Records the item dict passed to media_bytes."""

import json
import os

PATH = os.environ.get("MEDIA_ROW_PATH", "")


class Deck:
    id = "media_row"
    title = "Media row"
    directions = {"right": {"label": "Yes"}}

    def list_items(self, filter=None):
        return [
            {
                "id": "pic",
                "title": "Pic",
                "kind": "image",
                "fields": {"colour": "blue"},
                "image_path": "x.png",
            }
        ]

    def media_bytes(self, row, n=None):
        if PATH:
            with open(PATH, "w", encoding="utf-8") as handle:
                handle.write(json.dumps({"row": row, "n": n}))
        return (b"\x89PNG\r\n", "image/png")

    def handle(self, item_id, direction, note=None):
        return {"ok": True}
