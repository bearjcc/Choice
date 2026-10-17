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
    from choice.client_buffer import buffer_size_from_env

    config.client_buffer = buffer_size_from_env(config.client_buffer)
    if getattr(config, "server", None) is not None:
        _apply_server_env(config.server)


def _apply_server_env(server) -> None:
    from choice.env_config import env_flag, env_int

    host = os.environ.get("CHOICE_HOST")
    if host is not None and str(host).strip():
        server.network.host = str(host).strip()
    port = os.environ.get("CHOICE_PORT")
    if port is not None and str(port).strip():
        try:
            server.network.port = int(str(port).strip(), 10)
        except ValueError:
            pass
    base = os.environ.get("CHOICE_BASE_PATH")
    if base is not None:
        server.network.base_path = str(base).strip()
    pub = os.environ.get("CHOICE_PUBLIC_URL")
    if pub is not None:
        server.network.public_url = str(pub).strip()
    cert = os.environ.get("CHOICE_TLS_CERT")
    if cert is not None:
        server.network.tls_cert = str(cert).strip()
    key = os.environ.get("CHOICE_TLS_KEY")
    if key is not None:
        server.network.tls_key = str(key).strip()
    if env_flag("CHOICE_TRUST_FORWARDED"):
        server.network.trust_forwarded = True
    compress = os.environ.get("CHOICE_HTTP_COMPRESS")
    if compress is not None and str(compress).strip():
        server.http.compress = str(compress).strip().lower()
    server.http.request_queue_size = env_int(
        "CHOICE_HTTP_REQUEST_QUEUE_SIZE",
        server.http.request_queue_size,
    )
    if env_flag("CHOICE_IMAGE_TRANSCODE"):
        server.images.transcode = True
    fmt = os.environ.get("CHOICE_IMAGE_FORMAT")
    if fmt is not None and str(fmt).strip():
        server.images.format = str(fmt).strip().lower()
    server.images.max_edge = env_int("CHOICE_IMAGE_MAX_EDGE", server.images.max_edge)
    server.images.quality = env_int("CHOICE_IMAGE_QUALITY", server.images.quality)
    server.images.min_bytes = env_int("CHOICE_IMAGE_MIN_BYTES", server.images.min_bytes)
    server.images.min_edge = env_int("CHOICE_IMAGE_MIN_EDGE", server.images.min_edge)
    hw = os.environ.get("CHOICE_IMAGE_HW_ACCEL")
    if hw is not None and str(hw).strip():
        server.images.hw_accel = str(hw).strip().lower()
