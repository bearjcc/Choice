# SPDX-License-Identifier: AGPL-3.0-only
"""RSS and Atom feed source (read-only items)."""

from __future__ import annotations

import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from html import unescape
from pathlib import Path
from typing import Any

from choice.config import ConfigProblem
from choice.load import Deck, Direction, Item
from choice.sources.base import PreviewItem, Source

_FETCH_TIMEOUT = 20
_MAX_FEED = 2 * 1024 * 1024
_TAG = re.compile(r"<[^>]+>")


class RssSource(Source):
    def _feed_url(self) -> str:
        return str(self.options.get("url") or "").strip()

    def test(self) -> tuple[bool, str]:
        url = self._feed_url()
        if not url:
            return False, "Feed URL is required."
        try:
            data = _fetch(url)
            if b"<rss" in data[:500] or b"<feed" in data[:500]:
                return True, f"Feed fetched ({len(data)} bytes)."
            return False, "Response does not look like RSS or Atom."
        except Exception as exc:
            return False, str(exc)

    def preview(self, mount: str, limit: int = 5) -> list[PreviewItem]:
        try:
            entries = _parse_feed(_fetch(self._feed_url()))
        except Exception:
            return []
        out: list[PreviewItem] = []
        for entry in entries[:limit]:
            out.append(
                PreviewItem(
                    id=entry["id"], title=entry["title"], kind="card", body=entry["body"][:200]
                )
            )
        return out

    def open_deck(
        self,
        deck_id: str,
        title: str,
        mount: str,
        state_dir: Path,
        deck_options: dict[str, Any],
    ) -> Deck:
        url = self._feed_url()
        directions = {
            "left": Direction("left", "No", "no", does="label", color="#d64545"),
            "right": Direction("right", "Yes", "yes", does="label", color="#1f9d55"),
            "down": Direction("down", "Later", "later", later=True, does="label"),
        }

        def _load():
            entries = _parse_feed(_fetch(url))
            items = [
                Item(
                    id=entry["id"],
                    kind="card",
                    title=entry["title"],
                    body=entry["body"],
                    fields={"link": entry.get("link") or ""},
                )
                for entry in entries
            ]
            return items, []

        return Deck(
            id=deck_id,
            title=title,
            root=state_dir,
            state_dir=state_dir,
            directions=directions,
            buttons=[],
            blind=False,
            warnings=[],
            _load=_load,
        )


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(
        url, headers={"User-Agent": "Choice/0.2 (+https://github.com/bearjcc/choice)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT) as resp:
            data = resp.read(_MAX_FEED + 1)
    except urllib.error.URLError as exc:
        raise ConfigProblem(f"Feed fetch failed ({exc.reason})") from exc
    if len(data) > _MAX_FEED:
        raise ConfigProblem(f"Feed is larger than {_MAX_FEED} bytes.")
    return data


def _parse_feed(data: bytes) -> list[dict]:
    root = ET.fromstring(data)
    tag = root.tag.split("}")[-1].lower()
    if tag == "rss":
        channel = root.find("channel") or root.find("{*}channel")
        if channel is None:
            return []
        items = channel.findall("item") or channel.findall("{*}item")
        return [_rss_item(node, idx) for idx, node in enumerate(items)]
    if tag == "feed":
        entries = root.findall("{*}entry") or root.findall("entry")
        return [_atom_entry(node, idx) for idx, node in enumerate(entries)]
    return []


def _rss_item(node: ET.Element, idx: int) -> dict:
    title = _text(node, "title") or (f"Item {idx}")
    link = _text(node, "link")
    body = _text(node, "description") or ""
    guid = _text(node, "guid") or link or (f"item-{idx}")
    return {"id": _slug_id(guid), "title": title, "body": _plain(body), "link": link}


def _atom_entry(node: ET.Element, idx: int) -> dict:
    title = _text(node, "title") or (f"Entry {idx}")
    link = ""
    for child in node:
        if child.tag.split("}")[-1] == "link" and child.get("href"):
            link = child.get("href") or ""
            break
    body = _text(node, "summary") or _text(node, "content") or ""
    entry_id = _text(node, "id") or link or (f"entry-{idx}")
    return {"id": _slug_id(entry_id), "title": title, "body": _plain(body), "link": link}


def _text(node: ET.Element, local: str) -> str:
    for child in node:
        if child.tag.split("}")[-1] == local:
            return unescape((child.text or "") + (child.tail or "")).strip()
    return ""


def _plain(html: str) -> str:
    return unescape(_TAG.sub("", html)).strip()


def _slug_id(text: str) -> str:
    out = re.sub(r"[^a-zA-Z0-9_-]+", "-", text).strip("-").lower()
    return out[:80] or "item"
