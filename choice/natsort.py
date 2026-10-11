# SPDX-License-Identifier: AGPL-3.0-only
"""Natural sort keys for filenames and paths."""

from __future__ import annotations

import re

_CHUNK = re.compile(r"(\d+|\D+)")


def natural_key(text: str) -> tuple:
    parts: list[object] = []
    for chunk in _CHUNK.findall(str(text).lower()):
        if chunk.isdigit():
            parts.append(int(chunk))
        else:
            parts.append(chunk)
    return tuple(parts)
