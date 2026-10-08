# SPDX-License-Identifier: AGPL-3.0-only
"""Tell Immich when a card is binned or favourited.

Not wired up. To turn it on, add this to deck.json:

  "hook": {
    "command": ["python", "hook.py"],
    "required": true,
    "timeout_seconds": 30
  }

The card id is the Immich asset id. Replace the sample ids in items.jsonl.
Keep and Skip do not call Immich.

Set IMMICH_URL to the server origin, such as http://immich.example:2283.
Set IMMICH_API_KEY to a key with asset.read, asset.update, and asset.delete.

Bin moves the asset to Immich trash. It does not delete it. Undo restores it.
Favourite sets isFavorite. Undo puts the previous value back.
The local picture is only a preview. Choice does not download your library.
"""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

LOG = Path(".choice") / "immich.jsonl"
_ID = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-")


def main() -> None:
    body = json.load(sys.stdin)
    action = body.get("action")
    value = body.get("value")
    if action == "undo":
        undo(body)
        return
    if action != "decide" or value not in {"bin", "favourite"}:
        return
    asset = asset_id(body.get("item"))
    if value == "bin":
        call("DELETE", "/api/assets", {"ids": [asset], "force": False})
        remember(body, {"op": "bin", "asset": asset})
        return
    current = call("GET", "/api/assets/" + asset)
    was = bool(isinstance(current, dict) and current.get("isFavorite"))
    call("PUT", "/api/assets", {"ids": [asset], "isFavorite": True})
    remember(body, {"op": "favourite", "asset": asset, "was": was})


def undo(body: dict) -> None:
    found = find(body.get("decision_id"))
    if found is None:
        if body.get("value") in {"bin", "favourite"}:
            fail("No Immich note for this swipe, so it was not undone there.")
        return
    asset = found.get("asset")
    if found.get("op") == "bin":
        call("POST", "/api/trash/restore/assets", {"ids": [asset]})
        return
    if found.get("op") == "favourite":
        call("PUT", "/api/assets", {"ids": [asset], "isFavorite": bool(found.get("was"))})


def asset_id(raw) -> str:
    text = str(raw or "")
    if not text or any(char not in _ID for char in text):
        fail("Card id is not an Immich asset id.")
    return text


def remember(body: dict, extra: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    row = {"decision_id": body.get("decision_id"), **extra}
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


def find(decision) -> dict | None:
    if not decision or not LOG.is_file():
        return None
    found = None
    for line in LOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("decision_id") == decision:
            found = row
    return found


def call(method: str, path: str, payload: dict | None = None):
    base, key = config()
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        base + path,
        data=data,
        method=method,
        headers={
            "x-api-key": key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = _error_message(exc)
        fail("Immich HTTP %s%s" % (exc.code, (": " + detail) if detail else ""))
    except urllib.error.URLError as exc:
        fail("Cannot reach Immich (%s)" % exc.reason)
    if not raw:
        return None
    return json.loads(raw)


def config() -> tuple[str, str]:
    base = os.environ.get("IMMICH_URL", "").strip().rstrip("/")
    key = os.environ.get("IMMICH_API_KEY", "").strip()
    if not base or not key:
        fail("Set IMMICH_URL and IMMICH_API_KEY.")
    if not (base.startswith("http://") or base.startswith("https://")):
        fail("IMMICH_URL must start with http:// or https://.")
    return base, key


def _error_message(exc: urllib.error.HTTPError) -> str:
    try:
        message = json.loads(exc.read() or b"{}").get("message") or ""
    except (json.JSONDecodeError, OSError, UnicodeError):
        return ""
    return str(message)


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


if __name__ == "__main__":
    main()
