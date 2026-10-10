"""Plugin with a deliberate list_items delay for cold-load timing tests."""

import os
import time

_DELAY = float(os.environ.get("SLOW_LIST_DELAY", "0.25"))


class Deck:
    id = "slow_list"
    title = "Slow list"
    directions = {"right": {"label": "Yes"}}

    def list_items(self, filter=None):
        time.sleep(_DELAY)
        return [{"id": f"item-{i}", "title": f"Card {i}"} for i in range(40)]

    def handle(self, item_id, direction, note=None):
        return {"ok": True}
