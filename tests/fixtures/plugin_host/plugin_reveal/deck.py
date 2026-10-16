"""Pair deck with plugin reveal dict (voice_whichone-style)."""


class Deck:
    id = "plugin_reveal"
    title = "Plugin reveal"
    directions = {
        "left": {"label": "A", "value": "A"},
        "right": {"label": "B", "value": "B"},
        "down": {"label": "Skip", "value": "skip", "later": True},
    }

    def list_items(self, filter=None):
        return [
            {
                "id": "pair-1",
                "title": "Which voice?",
                "ab": {
                    "a": {"label": "A", "text": "Short clip"},
                    "b": {"label": "B", "text": "Long clip"},
                },
                "reveal": {
                    "real": "A",
                    "A_model": "human",
                    "B_model": "synthetic",
                },
            },
            {
                "id": "pair-2",
                "title": "Second",
                "ab": {
                    "a": {"label": "A", "text": "One"},
                    "b": {"label": "B", "text": "Two"},
                },
                "reveal": {"real": "B", "cat": "demo"},
            },
        ]

    def handle(self, item_id, direction, note=None):
        return {"ok": True}
