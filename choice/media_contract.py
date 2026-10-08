# SPDX-License-Identifier: AGPL-3.0-only
"""Shared media_bytes keyword contract for plugin-shaped adapters."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any


def accepts_host_media_call(fn: Callable[..., Any]) -> bool:
    """True when httpd may call media_bytes(item_id, item=row, index=n)."""
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return False
    params = sig.parameters
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return True
    return "item" in params or "index" in params or "n" in params
