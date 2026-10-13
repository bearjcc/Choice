"""Plugin fixture: single-select combobox + multi searchable list in flyout."""


class Deck:
    id = "combobox_filters"
    title = "Combobox filters"
    directions = {"right": {"label": "Yes"}}

    def filters(self):
        ratings = [
            {"value": f"r{i}", "label": f"Rating {i}", "count": 1} for i in range(28)
        ]
        tags = [
            {"value": f"t{i}", "label": f"Tag {i}", "count": 1} for i in range(24)
        ]
        return {
            "filters": [
                {
                    "id": "rating",
                    "label": "Rating",
                    "type": "tags",
                    "multi": False,
                    "options": ratings,
                },
                {
                    "id": "region",
                    "label": "Region",
                    "type": "tags",
                    "mode": "single",
                    "options": [
                        {"value": "eu", "label": "Europe"},
                        {"value": "na", "label": "North America"},
                        {"value": "ap", "label": "Asia Pacific"},
                        {"value": "sa", "label": "South America"},
                    ],
                },
                {
                    "id": "tag",
                    "label": "Tags",
                    "type": "tags",
                    "multi": True,
                    "match": ["all", "any"],
                    "options": tags,
                },
            ],
        }

    def list_items(self, filter=None):
        return [{"id": "card-1", "title": "Combobox filter card"}]

    def stats(self, filter=None):
        return {"match_count": 1, "count_label": "1 left"}

    def handle(self, item_id, direction, note=None):
        return {"ok": True}
