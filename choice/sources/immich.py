# SPDX-License-Identifier: AGPL-3.0-only
"""Immich album/search source (stream previews, trash as destructive action)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from choice.config import ConfigProblem, resolve_secret
from choice.load import Deck, DeckProblem, Direction, Item
from choice.sources.base import PreviewItem, Source

_FETCH_TIMEOUT = 30
_MAX_BODY = 8 * 1024 * 1024


class ImmichSource(Source):
    def _url(self) -> str:
        return str(self.options.get("url") or self.options.get("base_url") or "").rstrip("/")

    def _key(self) -> str:
        ref = self.options.get("api_key") or self.options.get("key") or "IMMICH_API_KEY"
        return resolve_secret(str(ref), self.app_config)

    def test(self) -> tuple[bool, str]:
        if not self._url():
            return False, "Immich URL is required."
        if not self._key():
            return False, "Set the API key env var (see api_key in config)."
        try:
            _api_get(self._url(), self._key(), "/api/server/ping")
            return True, "Immich reachable."
        except Exception as exc:
            return False, str(exc)

    def preview(self, mount: str, limit: int = 5) -> list[PreviewItem]:
        mount = self.resolve_mount(mount)
        try:
            assets = _list_assets(self, mount, limit=limit)
        except Exception:
            return []
        return [
            PreviewItem(
                id=str(a.get("id") or ""),
                title=str(a.get("originalFileName") or a.get("id") or ""),
                kind="image" if a.get("type") != "VIDEO" else "video",
            )
            for a in assets
        ]

    def open_deck(
        self,
        deck_id: str,
        title: str,
        mount: str,
        state_dir: Path,
        deck_options: dict[str, Any],
    ) -> Deck:
        mount = self.resolve_mount(mount)
        directions = {
            "left": Direction("left", "Bin", "bin", does="label", color="#d64545"),
            "right": Direction("right", "Keep", "keep", does="label", color="#1f9d55"),
            "down": Direction("down", "Skip", "skip", later=True, does="label", color="#56607a"),
        }
        adapter = _ImmichAdapter(self, mount)

        def _load():
            assets = _list_assets(self, mount, limit=int(deck_options.get("page_size") or 200))
            items = []
            for asset in assets:
                aid = str(asset.get("id") or "")
                if not aid:
                    continue
                items.append(
                    Item(
                        id=aid,
                        kind="image" if asset.get("type") != "VIDEO" else "video",
                        title=str(asset.get("originalFileName") or aid),
                        body="",
                        media_token=aid,
                        fields={"immich_id": aid},
                    )
                )
            return items, []

        deck = Deck(
            id=deck_id,
            title=title,
            root=state_dir,
            state_dir=state_dir,
            directions=directions,
            buttons=[],
            blind=False,
            warnings=[],
            _load=_load,
            plugin=adapter,
        )
        return deck


class _ImmichAdapter:
    """Minimal SwipePlugin-shaped object for act.py media/handle paths."""

    def __init__(self, source: ImmichSource, mount: str):
        self.source = source
        self.mount = mount
        self.deck_id = ""
        self.title = ""
        self.obj = self

    def list_items(self, filter: dict | None = None) -> list[dict]:
        return _list_assets(self.source, self.mount, limit=200)

    def handle(self, item_id: str, direction: str, note: str = "") -> dict:
        if direction == "left":
            try:
                _api_post(
                    self.source._url(),
                    self.source._key(),
                    "/api/assets/trash",
                    {"ids": [item_id], "force": False},
                )
            except Exception as exc:
                return {"ok": False, "message": str(exc)}
            return {"ok": True, "undo_token": item_id, "message": "Moved to Immich trash."}
        return {"ok": True, "undo_token": None, "message": "Recorded."}

    def undo(self, item_id: str, undo_token: str | None) -> dict:
        token = undo_token or item_id
        if not token:
            return {"ok": True, "message": "Undone."}
        try:
            _api_post(
                self.source._url(),
                self.source._key(),
                "/api/assets/trash/restore",
                {"ids": [token]},
            )
        except Exception as exc:
            return {"ok": False, "message": str(exc)}
        return {"ok": True, "message": "Restored from trash."}

    def media_bytes(self, item_id: str) -> tuple[bytes, str] | None:
        try:
            data, ctype = _api_get_raw(
                self.source._url(),
                self.source._key(),
                f"/api/assets/{item_id}/thumbnail?size=preview",
            )
            return data, ctype
        except Exception:
            return None


def _list_assets(source: ImmichSource, mount: str, limit: int) -> list[dict]:
    mount = (mount or "").strip()
    if mount.startswith("album:"):
        album_id = mount.split(":", 1)[1].strip()
        data = _api_get(source._url(), source._key(), f"/api/albums/{album_id}")
        assets = data.get("assets") or []
        return [a for a in assets if isinstance(a, dict)][:limit]
    query = mount or "search:"
    if query.startswith("search:"):
        body = {"size": min(limit, 250), "type": "IMAGE"}
        data = _api_post(source._url(), source._key(), "/api/search/metadata", body)
        items = (data.get("assets") or {}).get("items") or data.get("assets") or []
        return list(items)[:limit]
    raise ConfigProblem("Immich mount must be album:<id> or search:")


def _api_get(base: str, key: str, path: str) -> dict:
    return json.loads(_raw_request(base, key, "GET", path))


def _api_post(base: str, key: str, path: str, body: dict) -> dict:
    return json.loads(_raw_request(base, key, "POST", path, json.dumps(body).encode("utf-8")))


def _api_get_raw(base: str, key: str, path: str) -> tuple[bytes, str]:
    data = _raw_request(base, key, "GET", path)
    return data, "image/jpeg"


def _raw_request(base: str, key: str, method: str, path: str, body: bytes | None = None) -> bytes:
    req = urllib.request.Request(
        base + path,
        data=body,
        method=method,
        headers={"x-api-key": key, "Content-Type": "application/json", "Accept": "*/*"},
    )
    try:
        with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT) as resp:
            data = resp.read(_MAX_BODY + 1)
    except urllib.error.HTTPError as exc:
        raise DeckProblem(f"Immich HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise DeckProblem(f"Immich unreachable ({exc.reason})") from exc
    if len(data) > _MAX_BODY:
        raise DeckProblem("Immich response too large.")
    return data
