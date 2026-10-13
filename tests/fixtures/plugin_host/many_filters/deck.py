"""Plugin fixture: many filter options (faces + tags) for flyout UI tests."""


class Deck:
    id = "many_filters"
    title = "Many filters"
    directions = {"right": {"label": "Yes"}}

    def filters(self):
        faces = [
            {"value": f"face_{i}", "label": f"Face {i}", "count": 1} for i in range(38)
        ]
        tags = [
            {"value": f"tag_{i}", "label": f"Tag {i}", "count": 1} for i in range(58)
        ]
        return {
            "filters": [
                {
                    "id": "face",
                    "label": "Face",
                    "type": "tags",
                    "options": faces,
                    "multi": True,
                    "match": ["all", "any"],
                },
                {
                    "id": "tag",
                    "label": "Tags",
                    "type": "tags",
                    "options": tags,
                    "multi": True,
                    "match": ["all", "any"],
                },
            ],
            "sort": [{"value": "title", "label": "Title"}],
        }

    def list_items(self, filter=None):
        return [{"id": "card-1", "title": "Sample card for filter flyout"}]

    def stats(self, filter=None):
        return {"match_count": 1, "count_label": "1 left"}

    def handle(self, item_id, direction, note=None):
        return {"ok": True}
