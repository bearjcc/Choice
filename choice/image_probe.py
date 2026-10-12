# SPDX-License-Identifier: AGPL-3.0-only
"""Cheap openability checks for folder image scans."""

from __future__ import annotations

import logging
from pathlib import Path

from choice.bounded_cache import LruDict

_log = logging.getLogger(__name__)
_OPEN_CACHE: LruDict[str, tuple[int, int, bool]] = LruDict(8192)


def image_readable(path: Path) -> bool:
    """False for zero-byte files and images Pillow cannot open."""
    try:
        stat = path.stat()
    except OSError:
        return False
    if stat.st_size <= 0:
        return False
    key = str(path.resolve())
    hit = _OPEN_CACHE.get(key)
    if hit is not None and hit[0] == stat.st_mtime_ns and hit[1] == stat.st_size:
        return hit[2]
    ok = _probe_open(path)
    _OPEN_CACHE.set(key, (stat.st_mtime_ns, stat.st_size, ok))
    if not ok:
        _log.debug("skipping unreadable image %s", path)
    return ok


def _probe_open(path: Path) -> bool:
    try:
        from PIL import Image
    except ImportError:
        return True
    _register_optional_codecs()
    try:
        from choice.source_reads import hold_source_read

        with hold_source_read(path):
            with Image.open(path) as image:
                image.verify()
        return True
    except Exception:
        return False


def _register_optional_codecs() -> None:
    from choice.optional_codecs import register_optional_codecs

    register_optional_codecs()
