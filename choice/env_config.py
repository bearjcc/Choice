# SPDX-License-Identifier: AGPL-3.0-only
"""CHOICE_* environment overrides for config and CLI."""

from __future__ import annotations

import os

from choice.config import AppConfig, _expand


def env_flag(name: str) -> bool:
    value = os.environ.get(name, "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(str(raw).strip(), 10)
    except ValueError:
        return default


def apply_config_env(config: AppConfig) -> None:
    """Overlay choice.toml fields from CHOICE_* (CLI flags still win where applicable)."""
    state = os.environ.get("CHOICE_STATE_DIR")
    if state:
        config.state_dir = _expand(state, config.path.parent)
    secrets = os.environ.get("CHOICE_SECRETS_FILE")
    if secrets:
        config.secrets_file = _expand(secrets, config.path.parent)
    users = os.environ.get("CHOICE_USERS_FILE")
    if users:
        config.roster_path = _expand(users, config.path.parent)
    title = os.environ.get("CHOICE_TITLE")
    if title is not None and str(title).strip():
        config.app_title = str(title).strip()
