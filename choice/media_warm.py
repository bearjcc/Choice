# SPDX-License-Identifier: AGPL-3.0-only
"""Background downsample for upcoming cards (single worker pool)."""

from __future__ import annotations

import atexit
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from choice.media import prepare_file, snap_edge

_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="choice-warm")
atexit.register(_POOL.shutdown, wait=False)


def warm_file_paths(paths: list[Path], cache_dir: Path, width: int | None) -> None:
    edge = snap_edge(width)
    for path in paths:
        if not path or not path.is_file():
            continue
        _POOL.submit(_warm_one, path.resolve(), cache_dir.resolve(), edge)


def _warm_one(path: Path, cache_dir: Path, edge: int | None) -> None:
    try:
        prepare_file(path, cache_dir, width=edge, etag_version="warm")
    except Exception:
        return
