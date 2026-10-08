class Deck:
    id = "plugin_decided_mix"
    title = "Plugin decided mix"
    directions = {"right": {"label": "Keep"}}

    def list_items(self, filter=None):
        return [
            {"id": "open-a", "title": "Open A"},
            {"id": "open-b", "title": "Open B"},
            {"id": "plug-1", "title": "Plugin done 1", "decided": True},
            {"id": "plug-2", "title": "Plugin done 2", "decided": True},
        ]

    def handle(self, item_id, direction, note=None):
        return {"ok": True}
