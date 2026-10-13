# SPDX-License-Identifier: AGPL-3.0-only
"""Optional gzip/brotli for JSON/text HTTP bodies."""

from __future__ import annotations

import gzip
from typing import Callable

try:
    import brotli
except ImportError:  # pragma: no cover
    brotli = None


def compress_body(data: bytes, mode: str, accept_encoding: str) -> tuple[bytes, str | None]:
    """Return (body, content_encoding). mode: off, gzip, brotli, both."""
    mode = (mode or "off").lower()
    if mode == "off" or len(data) < 256:
        return data, None
    accept = (accept_encoding or "").lower()
    if mode in {"brotli", "both"} and brotli is not None and "br" in accept:
        return brotli.compress(data), "br"
    if mode in {"gzip", "both"} and "gzip" in accept:
        return gzip.compress(data, compresslevel=5), "gzip"
    return data, None


def wrap_json_sender(send_json: Callable[..., None], compress_mode: str):
    """Decorator factory — not used; httpd calls compress_body directly."""

    return send_json
