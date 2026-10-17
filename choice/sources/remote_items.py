# SPDX-License-Identifier: AGPL-3.0-only
"""Shared preview/load row builders for Immich, RSS/Atom, and WebDAV sources."""

from __future__ import annotations

from choice.load import Item
from choice.sources.base import PreviewItem


def immich_asset_fields(asset: dict) -> tuple[str, str, str]:
    """Return (id, title, kind) for one Immich asset dict."""
    aid = str(asset.get("id") or "")
    title = str(asset.get("originalFileName") or aid)
    kind = "image" if asset.get("type") != "VIDEO" else "video"
    return aid, title, kind


def immich_preview_item(asset: dict) -> PreviewItem:
    aid, title, kind = immich_asset_fields(asset)
    return PreviewItem(id=aid, title=title, kind=kind)


def immich_deck_item(asset: dict) -> Item:
    aid, title, kind = immich_asset_fields(asset)
    row = {
        "id": aid,
        "title": title,
        "kind": kind,
        "image_path": f"immich:{aid}",
    }
    return Item(
        id=aid,
        kind=kind,
        title=title,
        body="",
        media_token=aid,
        fields={"immich_id": aid},
        plugin_media=True,
        plugin_row=row,
    )


def feed_entry_preview(entry: dict) -> PreviewItem:
    body = entry.get("body") or ""
    return PreviewItem(
        id=entry["id"],
        title=entry["title"],
        kind="card",
        body=body[:200],
    )


def feed_entry_item(entry: dict) -> Item:
    return Item(
        id=entry["id"],
        kind="card",
        title=entry["title"],
        body=entry["body"],
        fields={"link": entry.get("link") or ""},
    )


def webdav_href_id(href: str) -> str:
    return href.strip("/").replace("/", "__") or "root"


def webdav_href_title(href: str) -> str:
    return href.rstrip("/").split("/")[-1]


def webdav_preview_item(href: str) -> PreviewItem:
    return PreviewItem(
        id=webdav_href_id(href),
        title=webdav_href_title(href),
        kind="image",
    )


def webdav_deck_item(href: str) -> Item:
    name = webdav_href_title(href)
    item_id = webdav_href_id(href)
    return Item(
        id=item_id,
        kind="image",
        title=name,
        body="",
        media_token=href,
        fields={"href": href},
    )
