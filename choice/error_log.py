# SPDX-License-Identifier: AGPL-3.0-only
"""Rotating error log under the config state directory."""

from __future__ import annotations

import logging
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG: logging.Logger | None = None
_LOG_PATH: Path | None = None

_MAX_BYTES = 2_000_000
_BACKUP_COUNT = 5


def configure(state_dir: Path) -> Path:
    """Attach a rotating file handler; return the log path."""
    global _LOG, _LOG_PATH
    state_dir = state_dir.expanduser().resolve()
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / "choice-errors.log"
    if _LOG_PATH == path and _LOG is not None:
        return path

    logger = logging.getLogger("choice.errors")
    logger.setLevel(logging.ERROR)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    handler = RotatingFileHandler(
        path,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
        delay=True,
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S")
    )
    logger.addHandler(handler)
    _LOG = logger
    _LOG_PATH = path
    return path


def log_path() -> Path | None:
    return _LOG_PATH


def log_exception(kind: str, exc: BaseException | None = None, *, extra: str = "") -> None:
    if _LOG is None:
        return
    parts = [kind]
    if extra:
        parts.append(extra)
    if exc is not None:
        parts.append(f"{type(exc).__name__}: {exc}")
    message = " | ".join(parts)
    if exc is not None:
        _LOG.error("%s\n%s", message, "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    else:
        _LOG.error("%s", message)


def log_traceback(kind: str, tb_text: str) -> None:
    if _LOG is None:
        return
    _LOG.error("%s\n%s", kind, tb_text.rstrip())


def user_detail_hint() -> str:
    if _LOG_PATH is not None:
        return f"Details are in {_LOG_PATH}."
    return "Details are in choice-errors.log in your state directory."


def shutdown() -> None:
    """Close log handlers (tests / shutdown)."""
    global _LOG, _LOG_PATH
    if _LOG is not None:
        for handler in list(_LOG.handlers):
            _LOG.removeHandler(handler)
            handler.close()
    _LOG = None
    _LOG_PATH = None
