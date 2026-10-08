# SPDX-License-Identifier: AGPL-3.0-only
"""Shrink a photo for the phone, if Pillow happens to be installed.

Without Pillow, Choice serves the original file. Install Pillow when a
camera dump is slow over the network. The cache lives in `.choice/cache`
and is safe to delete.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

_MAX = 1600
_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".avif": "image/avif",
}


def content_type(path: Path) -> str:
    return _TYPES.get(path.suffix.lower(), "application/octet-stream")


def view_path(src: Path, cache_dir: Path) -> Path:
    """Return a file the browser can show. Falls back to src on any problem."""
    if src.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
        return src
    try:
        stat = src.stat()
    except OSError:
        return src
    try:
        from PIL import Image
    except ImportError:
        return src
    digest = hashlib.sha256(str(src.resolve()).encode("utf-8")).hexdigest()[:16]
    dest = cache_dir / ("%s-%d-%d.jpg" % (digest, stat.st_mtime_ns, stat.st_size))
    if dest.is_file():
        return dest
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        with Image.open(src) as image:
            image = image.convert("RGB")
            image.thumbnail((_MAX, _MAX))
            image.save(dest, "JPEG", quality=85)
    except Exception:
        return src
    return dest
