# SPDX-License-Identifier: AGPL-3.0-only
"""Shared folder path → Item construction."""

from __future__ import annotations

from pathlib import Path

from choice.load import Item, _is_image, _mtime, _size_text

_HEIC_BODY = "HEIC photo. Choice will not preview it. A decision still applies to the file."


def folder_item_from_path(rel_id: str, path: Path) -> Item:
    """Build one folder pile Item from a resolved file path and relative id."""
    path = path.resolve()
    kind = "image" if _is_image(path) else "file"
    title = path.name
    body = _size_text(path) if kind == "file" else ""
    if path.suffix.lower() == ".heic":
        kind = "file"
        body = _HEIC_BODY
    return Item(
        id=rel_id,
        kind=kind,
        title=title,
        body=body,
        path=path,
        media_token=str(_mtime(path)),
        fields={"file": rel_id},
    )
