# SPDX-License-Identifier: AGPL-3.0-only
"""WebDAV folder source (image files over DAV)."""

from __future__ import annotations

import base64
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from choice.config import ConfigProblem, resolve_secret
from choice.load import Deck, Direction, Item
from choice.sources.base import PreviewItem, Source

_FETCH_TIMEOUT = 30
_MAX_LIST = 512 * 1024
_IMG = re.compile(r"\.(jpe?g|png|gif|webp|avif|bmp)$", re.I)


class WebDavSource(Source):
    def _base(self) -> str:
        return str(self.options.get("url") or "").rstrip("/")

    def _auth_header(self) -> str:
        user_ref = self.options.get("username") or self.options.get("user") or "WEBDAV_USER"
        pass_ref = self.options.get("password") or "WEBDAV_PASSWORD"
        user = resolve_secret(str(user_ref), self.app_config)
        password = resolve_secret(str(pass_ref), self.app_config)
        if not user:
            return ""
        token = base64.b64encode((f"{user}:{password}").encode()).decode("ascii")
        return "Basic " + token

    def test(self) -> tuple[bool, str]:
        if not self._base():
            return False, "WebDAV URL is required."
        try:
            _propfind(self._base(), self._auth_header(), depth="0")
            return True, "WebDAV OK."
        except Exception as exc:
            return False, str(exc)

    def preview(self, mount: str, limit: int = 5) -> list[PreviewItem]:
        try:
            paths = _list_images(self, self.resolve_mount(mount))
        except Exception:
            return []
        out: list[PreviewItem] = []
        from choice.sources.remote_items import webdav_preview_item

        for href in paths[:limit]:
            out.append(webdav_preview_item(href))
        return out

    def open_deck(
        self,
        deck_id: str,
        title: str,
        mount: str,
        state_dir: Path,
        deck_options: dict[str, Any],
    ) -> Deck:
        mount = self.resolve_mount(mount)
        adapter = _WebDavMedia(self, mount)
        directions = {
            "left": Direction("left", "No", "no", does="label", color="#d64545"),
            "right": Direction("right", "Yes", "yes", does="label", color="#1f9d55"),
            "down": Direction("down", "Skip", "skip", later=True, does="label"),
        }

        def _load():
            paths = _list_images(self, mount)
            items = []
            from choice.sources.remote_items import webdav_deck_item

            for href in paths:
                items.append(webdav_deck_item(href))
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


class _WebDavMedia:
    def __init__(self, source: WebDavSource, mount: str):
        self.source = source
        self.mount = mount
        self.obj = self

    def media_bytes(
        self,
        item_id: str,
        item: dict | None = None,
        index: int | None = None,
    ) -> tuple[bytes, str] | None:
        href = item_id if item_id.startswith("/") else "/" + item_id
        url = self.source._base() + href
        req = urllib.request.Request(url, headers={"Authorization": self.source._auth_header()})
        try:
            with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT) as resp:
                data = resp.read(8 * 1024 * 1024 + 1)
        except urllib.error.URLError:
            return None
        if len(data) > 8 * 1024 * 1024:
            return None
        ctype = resp.headers.get("Content-Type") or "application/octet-stream"
        return data, ctype.split(";")[0]


def _list_images(source: WebDavSource, mount: str) -> list[str]:
    base = source._base()
    path = mount if mount.startswith("/") else ("/" + mount if mount else "/")
    url = base + path
    xml = _propfind(url, source._auth_header(), depth="1")
    root = ET.fromstring(xml)
    hrefs: list[str] = []
    for resp in root.findall("{DAV:}response"):
        href = resp.find("{DAV:}href")
        if href is None or not href.text:
            continue
        text = href.text
        if not _IMG.search(text):
            continue
        hrefs.append(text)
    return sorted(hrefs)


def _propfind(url: str, auth: str, depth: str) -> bytes:
    body = (
        b'<?xml version="1.0" encoding="utf-8" ?>'
        b'<propfind xmlns="DAV:"><prop><resourcetype/></prop></propfind>'
    )
    req = urllib.request.Request(
        url,
        data=body,
        method="PROPFIND",
        headers={
            "Authorization": auth,
            "Depth": depth,
            "Content-Type": "application/xml",
        },
    )
    with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT) as resp:
        data = resp.read(_MAX_LIST + 1)
    if len(data) > _MAX_LIST:
        raise ConfigProblem("WebDAV listing too large.")
    return data


