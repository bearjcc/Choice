# SPDX-License-Identifier: AGPL-3.0-only
"""Loopback smoke test against a running Choice server."""

import json
import sys
import urllib.request

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8842
BASE = f"http://127.0.0.1:{PORT}"


def get(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    health = get("/api/health")
    assert health.get("ok"), health
    index = get("/api/index")
    assert index.get("ok"), index
    assert len(index.get("decks") or []) >= 3, index
    deck_id = index["decks"][0]["id"]
    items = get(f"/api/decks/{deck_id}/items?pending=1")
    assert items.get("ok"), items
    assert items.get("items"), items
    print("smoke ok", deck_id, len(items["items"]), "cards")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
