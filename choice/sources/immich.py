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
_PAGE_SIZE = 100


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
            _api_json(self._url(), self._key(), "GET", "/api/server/ping")
            return True, "Immich reachable."
        except Exception as exc:
            return False, str(exc)

    def preview(self, mount: str, limit: int = 5) -> list[PreviewItem]:
        mount = self.resolve_mount(mount)
        try:
            assets = _list_assets(self, mount, limit=limit)
        except Exception:
            return []
        return [_preview_row(a) for a in assets]

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
        if bool(deck_options.get("favourite")):
            directions["up"] = Direction(
                "up", "Favourite", "favourite", does="label", color="#c9a227"
            )
        adapter = _ImmichAdapter(self, mount, deck_options)

        def _load():
            page_size = int(deck_options.get("page_size") or _PAGE_SIZE)
            assets = _list_assets(self, mount, limit=page_size)
            items = [_item_from_asset(asset) for asset in assets]
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

    def __init__(self, source: ImmichSource, mount: str, deck_options: dict[str, Any]):
        self.source = source
        self.mount = mount
        self.deck_options = deck_options
        self.deck_id = ""
        self.title = ""
        self.obj = self

    def list_items(self, filter: dict | None = None) -> list[dict]:
        limit = int(self.deck_options.get("page_size") or _PAGE_SIZE)
        return _list_assets(self.source, self.mount, limit=limit)

    def handle(self, item_id: str, direction: str, note: str = "") -> dict:
        if direction == "left":
            try:
                _api_json(
                    self.source._url(),
                    self.source._key(),
                    "DELETE",
                    "/api/assets",
                    {"ids": [item_id], "force": False},
                )
            except Exception as exc:
                return {"ok": False, "message": str(exc)}
            return {"ok": True, "undo_token": item_id, "message": "Moved to Immich trash."}
        if direction == "up":
            try:
                current = _api_json(
                    self.source._url(),
                    self.source._key(),
                    "GET",
                    f"/api/assets/{item_id}",
                )
                was = bool(isinstance(current, dict) and current.get("isFavorite"))
                _api_json(
                    self.source._url(),
                    self.source._key(),
                    "PUT",
                    "/api/assets",
                    {"ids": [item_id], "isFavorite": True},
                )
            except Exception as exc:
                return {"ok": False, "message": str(exc)}
            return {
                "ok": True,
                "undo_token": json.dumps({"favourite_was": was}),
                "message": "Favourited in Immich.",
            }
        return {"ok": True, "undo_token": None, "message": "Recorded."}

    def undo(self, item_id: str, undo_token: str | None) -> dict:
        if undo_token and str(undo_token).startswith("{"):
            try:
                payload = json.loads(str(undo_token))
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict) and "favourite_was" in payload:
                try:
                    _api_json(
                        self.source._url(),
                        self.source._key(),
                        "PUT",
                        "/api/assets",
                        {
                            "ids": [item_id],
                            "isFavorite": bool(payload.get("favourite_was")),
                        },
                    )
                except Exception as exc:
                    return {"ok": False, "message": str(exc)}
                return {"ok": True, "message": "Favourite restored."}
        token = undo_token or item_id
        if not token:
            return {"ok": True, "message": "Undone."}
        try:
            _api_json(
                self.source._url(),
                self.source._key(),
                "POST",
                "/api/trash/restore/assets",
                {"ids": [token]},
            )
        except Exception as exc:
            return {"ok": False, "message": str(exc)}
        return {"ok": True, "message": "Restored from trash."}

    def media_bytes(
        self,
        item_id: str,
        item: dict | None = None,
        index: int | None = None,
    ) -> tuple[bytes, str] | None:
        aid = item_id
        if item and item.get("id"):
            aid = str(item["id"])
        try:
            return _api_get_raw(
                self.source._url(),
                self.source._key(),
                f"/api/assets/{aid}/thumbnail?size=preview",
            )
        except Exception:
            return None


def _preview_row(asset: dict) -> PreviewItem:
    aid = str(asset.get("id") or "")
    return PreviewItem(
        id=aid,
        title=str(asset.get("originalFileName") or aid),
        kind="image" if asset.get("type") != "VIDEO" else "video",
    )


def _item_from_asset(asset: dict) -> Item:
    aid = str(asset.get("id") or "")
    row = {
        "id": aid,
        "title": str(asset.get("originalFileName") or aid),
        "kind": "image" if asset.get("type") != "VIDEO" else "video",
        "image_path": f"immich:{aid}",
    }
    return Item(
        id=aid,
        kind=row["kind"],
        title=row["title"],
        body="",
        media_token=aid,
        fields={"immich_id": aid},
        plugin_media=True,
        plugin_row=row,
    )


def _list_assets(source: ImmichSource, mount: str, limit: int) -> list[dict]:
    mount = (mount or "").strip()
    limit = max(1, int(limit or _PAGE_SIZE))
    if mount.startswith("album:"):
        album_id = mount.split(":", 1)[1].strip()
        if not album_id:
            raise ConfigProblem("Immich album mount needs album:<id>.")
        return _search_metadata(
            source,
            {"albumIds": [album_id]},
            limit=limit,
            exclude_archived=bool(source.options.get("exclude_archived", True)),
        )
    query = mount or "search:"
    if query.startswith("search:"):
        text = query.split(":", 1)[1].strip()
        if text:
            smart = _search_smart(source, text, limit=limit)
            if smart is not None:
                return smart
            return _search_metadata(
                source,
                {"description": text},
                limit=limit,
                exclude_archived=bool(source.options.get("exclude_archived", True)),
            )
        return _search_metadata(
            source,
            {},
            limit=limit,
            exclude_archived=bool(source.options.get("exclude_archived", True)),
        )
    raise ConfigProblem("Immich mount must be album:<id> or search:<query>.")


def _search_smart(source: ImmichSource, query: str, limit: int) -> list[dict] | None:
    try:
        return _collect_pages(
            source,
            "/api/search/smart",
            {"query": query},
            limit=limit,
            exclude_archived=bool(source.options.get("exclude_archived", True)),
        )
    except DeckProblem as exc:
        if "HTTP 404" in str(exc):
            return None
        raise


def _search_metadata(
    source: ImmichSource,
    filters: dict,
    limit: int,
    exclude_archived: bool,
) -> list[dict]:
    return _collect_pages(
        source,
        "/api/search/metadata",
        filters,
        limit=limit,
        exclude_archived=exclude_archived,
    )


def _collect_pages(
    source: ImmichSource,
    path: str,
    filters: dict,
    limit: int,
    exclude_archived: bool,
) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    page = 1
    page_size = min(250, max(limit, 1))
    while len(out) < limit:
        body = {**filters, "size": page_size, "page": page}
        data = _api_json(source._url(), source._key(), "POST", path, body)
        items = _extract_assets(data)
        if not items:
            break
        added = 0
        for asset in items:
            if not isinstance(asset, dict):
                continue
            aid = str(asset.get("id") or "")
            if aid and aid in seen:
                continue
            if not _asset_visible(asset, exclude_archived):
                continue
            if aid:
                seen.add(aid)
            out.append(asset)
            added += 1
            if len(out) >= limit:
                break
        if len(items) < page_size:
            break
        if added == 0 and len(items) > 0:
            page += 1
            continue
        page += 1
    return out[:limit]


def _extract_assets(data: dict) -> list[dict]:
    assets = data.get("assets")
    if isinstance(assets, dict):
        items = assets.get("items")
        if isinstance(items, list):
            return items
    if isinstance(assets, list):
        return assets
    items = data.get("items")
    if isinstance(items, list):
        return items
    return []


def _asset_visible(asset: dict, exclude_archived: bool) -> bool:
    if asset.get("deletedAt"):
        return False
    if asset.get("isTrashed"):
        return False
    visibility = asset.get("visibility")
    if asset.get("isHidden") or visibility == "hidden":
        return False
    if asset.get("isLocked") or visibility == "locked":
        return False
    if exclude_archived and asset.get("isArchived"):
        return False
    return True


def _api_json(
    base: str,
    key: str,
    method: str,
    path: str,
    body: dict | None = None,
) -> dict:
    payload = None if body is None else json.dumps(body).encode("utf-8")
    data, _ctype, code = _raw_request(base, key, method, path, payload)
    if code == 204 or not data:
        return {}
    try:
        parsed = json.loads(data.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise DeckProblem(f"Immich returned invalid JSON on {path}.") from exc
    if not isinstance(parsed, dict):
        raise DeckProblem(f"Immich returned unexpected JSON on {path}.")
    return parsed


def _api_get_raw(base: str, key: str, path: str) -> tuple[bytes, str]:
    data, ctype, _code = _raw_request(base, key, "GET", path)
    return data, ctype or "application/octet-stream"


def _raw_request(
    base: str,
    key: str,
    method: str,
    path: str,
    body: bytes | None = None,
) -> tuple[bytes, str, int]:
    headers = {"x-api-key": key, "Accept": "*/*"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(base + path, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT) as resp:
            code = int(getattr(resp, "status", 200) or 200)
            ctype = resp.headers.get("Content-Type") or ""
            if "application/json" in ctype or path.endswith("/ping"):
                data = resp.read(_MAX_BODY + 1)
            else:
                data = resp.read(_MAX_BODY + 1)
    except urllib.error.HTTPError as exc:
        raise _http_problem(exc) from exc
    except urllib.error.URLError as exc:
        raise DeckProblem(f"Immich unreachable ({exc.reason})") from exc
    if len(data) > _MAX_BODY:
        raise DeckProblem("Immich response too large.")
    return data, ctype.split(";")[0].strip().lower(), code


def _http_problem(exc: urllib.error.HTTPError) -> DeckProblem:
    detail = _error_message(exc)
    if detail:
        return DeckProblem(f"Immich HTTP {exc.code}: {detail}")
    return DeckProblem(f"Immich HTTP {exc.code}")


def _error_message(exc: urllib.error.HTTPError) -> str:
    try:
        raw = exc.read() or b""
    except OSError:
        return ""
    if not raw:
        return ""
    try:
        payload = json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        text = raw.decode("utf-8", errors="replace").strip()
        return text[:200]
    if isinstance(payload, dict):
        message = payload.get("message") or payload.get("error")
        if message:
            return str(message)
    return ""
