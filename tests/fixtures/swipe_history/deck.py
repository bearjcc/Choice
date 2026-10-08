"""Minimal swipe plugin for legacy log tests."""


class Deck:
    id = "swipe_history"
    title = "Swipe history fixture"
    directions = {
        "right": {"label": "Yes"},
        "left": {"label": "No"},
        "down": {"label": "Skip"},
    }

    def list_items(self, filter=None):
        return [
            {"id": "a", "title": "A"},
            {"id": "b", "title": "B"},
            {"id": "c", "title": "C"},
        ]

    def handle(self, item_id, direction, note=None):
        return {"ok": True, "message": direction}

    def undo(self, item_id, undo_token):
        return {"ok": True, "message": "undone"}
