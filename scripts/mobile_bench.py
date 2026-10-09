#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Rough mobile timings: HTTP round-trips for a tiny synthetic deck."""

from __future__ import annotations

import json
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

from choice.httpd import ChoiceSite


def _post_json(url: str, payload: dict) -> None:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=30).read()


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "a.jpg").write_bytes(b"\xff\xd8\xff" + b"x" * 200)
        (root / "b.jpg").write_bytes(b"\xff\xd8\xff" + b"y" * 200)
        cfg = root / "choice.toml"
        cfg.write_text(
            f"""
[state]
dir = "state"

[[sources]]
id = "f"
type = "folder"
path = "{root.as_posix()}"

[[decks]]
id = "d"
title = "Bench"
source = "f"
mount = "."
type = "images"
""".strip(),
            encoding="utf-8",
        )
        httpd = ChoiceSite(("127.0.0.1", 0), root, config_path=cfg)
        port = httpd.server_address[1]
        base = f"http://127.0.0.1:{port}"
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()

        def get(path: str) -> float:
            start = time.perf_counter()
            urllib.request.urlopen(base + path, timeout=30).read()
            return time.perf_counter() - start

        index_ms = get("/api/index") * 1000
        items_ms = get("/api/decks/d/items?pending=1&w=960") * 1000
        decide_start = time.perf_counter()
        _post_json(
            base + "/api/decks/d/decide",
            {"item": "a.jpg", "direction": "right", "note": ""},
        )
        decide_ms = (time.perf_counter() - decide_start) * 1000
        items2_ms = get("/api/decks/d/items?pending=1&w=960") * 1000
        print(json.dumps({
            "index_ms": round(index_ms, 1),
            "first_items_ms": round(items_ms, 1),
            "decide_ms": round(decide_ms, 1),
            "items_after_decide_ms": round(items2_ms, 1),
            "note": "UI now shows next card before decide_ms completes (optimistic).",
        }, indent=2))
        httpd.shutdown()


if __name__ == "__main__":
    main()
