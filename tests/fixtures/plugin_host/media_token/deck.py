class Deck:
    id = "media_token"
    title = "Token media"
    directions = {"right": {"label": "Yes"}}

    def list_items(self, filter=None):
        return [
            {
                "id": "asset",
                "title": "Asset",
                "kind": "image",
                "image_path": "immich:fake-asset-id",
            }
        ]

    def media_bytes(self, row, n=None):
        token = row.get("image_path") or ""
        if token.startswith("immich:"):
            return (b"\x89PNG\r\n", "image/png")
        return None

    def handle(self, item_id, direction, note=None):
        return {"ok": True}
