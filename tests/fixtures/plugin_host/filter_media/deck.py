"""Plugin: list_items depends on filter; media_bytes only for filtered ids."""


class Deck:
    id = "filter_media"
    title = "Filter media"
    directions = {"right": {"label": "Yes"}}

    _PNG = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f"
        b"\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    def filters(self):
        return {
            "filters": [
                {
                    "id": "tag",
                    "label": "Tag",
                    "type": "tags",
                    "multi": False,
                    "options": [{"value": "a", "label": "A"}],
                }
            ],
        }

    def list_items(self, filter=None):
        if not filter:
            return [{"id": "unfiltered", "title": "No filter"}]
        tag = filter.get("tag") or {}
        if tag.get("values") == ["a"]:
            return [{"id": "filtered-card", "title": "Filtered card"}]
        return []

    def media_bytes(self, row, n=None, side=None, item=None, index=None):
        row = item if isinstance(item, dict) else row
        if isinstance(row, dict) and row.get("id") == "filtered-card":
            return self._PNG, "image/png"
        return None

    def handle(self, item_id, direction, note=None):
        return {"ok": True}
