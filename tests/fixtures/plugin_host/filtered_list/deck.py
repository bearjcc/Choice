"""Plugin fixture: deck-declared filters for list_items / stats."""


class Deck:
    id = "filtered_list"
    title = "Filtered"
    directions = {"right": {"label": "Yes"}}

    _rows = [
        {"id": "1", "title": "One", "tags": ["a"]},
        {"id": "2", "title": "Two", "tags": ["a", "b"]},
        {"id": "3", "title": "Three", "tags": ["b"]},
    ]

    def filters(self):
        return {
            "filters": [
                {
                    "id": "tag",
                    "label": "Tag",
                    "type": "tags",
                    "options": [
                        {"value": "a", "label": "A", "count": 2},
                        {"value": "b", "label": "B", "count": 2},
                    ],
                    "multi": True,
                    "match": ["all", "any"],
                }
            ],
            "sort": [{"value": "title", "label": "Title"}],
        }

    def _match_row(self, row, filt):
        tag = filt.get("tag") or {}
        values = tag.get("values") or []
        if not values:
            return True
        tags = set(row.get("tags") or [])
        mode = tag.get("match") or "any"
        if mode == "all":
            return all(v in tags for v in values)
        return any(v in tags for v in values)

    def list_items(self, filter=None):
        rows = list(self._rows)
        if filter:
            rows = [r for r in rows if self._match_row(r, filter)]
            sort_key = filter.get("_sort")
            if sort_key == "title":
                rows = sorted(rows, key=lambda r: r["title"])
        return [{"id": r["id"], "title": r["title"]} for r in rows]

    def stats(self, filter=None):
        rows = self.list_items(filter=filter)
        hint = "filtered" if filter else "all"
        return {
            "match_count": len(rows),
            "hint": hint,
            "count_label": str(len(rows)) + " match",
        }

    def handle(self, item_id, direction, note=None):
        return {"ok": True}
