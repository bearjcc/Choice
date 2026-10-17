# SPDX-License-Identifier: AGPL-3.0-only
"""Server-wide settings in choice.toml ([network], [http], [images], [service])."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from choice.config import ConfigProblem, _toml_str

VALID_COMPRESS = {"off", "gzip", "brotli", "both"}
VALID_IMAGE_FORMAT = {"original", "webp", "avif", "jxl"}
VALID_HW = {"off", "auto", "pillow", "ffmpeg", "vips"}


@dataclass
class NetworkSettings:
    host: str = "127.0.0.1"
    port: int = 8741
    base_path: str = ""
    public_url: str = ""
    tls_cert: str = ""
    tls_key: str = ""
    trust_forwarded: bool = False

    def public_dict(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "base_path": self.base_path,
            "public_url": self.public_url,
            "tls_cert": self.tls_cert,
            "tls_key": self.tls_key,
            "trust_forwarded": self.trust_forwarded,
        }


@dataclass
class HttpSettings:
    compress: str = "gzip"
    request_queue_size: int = 128

    def public_dict(self) -> dict[str, Any]:
        return {
            "compress": self.compress,
            "request_queue_size": self.request_queue_size,
        }


@dataclass
class ImageDeliverySettings:
    transcode: bool = False
    format: str = "original"
    max_edge: int = 2048
    quality: int = 85
    min_bytes: int = 512_000
    min_edge: int = 1280
    hw_accel: str = "auto"

    def public_dict(self) -> dict[str, Any]:
        return {
            "transcode": self.transcode,
            "format": self.format,
            "max_edge": self.max_edge,
            "quality": self.quality,
            "min_bytes": self.min_bytes,
            "min_edge": self.min_edge,
            "hw_accel": self.hw_accel,
        }


@dataclass
class ServerSettings:
    network: NetworkSettings = field(default_factory=NetworkSettings)
    http: HttpSettings = field(default_factory=HttpSettings)
    images: ImageDeliverySettings = field(default_factory=ImageDeliverySettings)

    def public_dict(self) -> dict[str, Any]:
        return {
            "network": self.network.public_dict(),
            "http": self.http.public_dict(),
            "images": self.images.public_dict(),
        }


def parse_server_settings(raw: dict) -> ServerSettings:
    net = _parse_network(raw.get("network") if isinstance(raw.get("network"), dict) else {})
    http = _parse_http(raw.get("http") if isinstance(raw.get("http"), dict) else {})
    images = _parse_images(raw.get("images") if isinstance(raw.get("images"), dict) else {})
    return ServerSettings(network=net, http=http, images=images)


def _parse_network(block: dict) -> NetworkSettings:
    host = str(block.get("host") or "127.0.0.1").strip() or "127.0.0.1"
    port = _int(block.get("port"), 8741, 1, 65535)
    base_path = str(block.get("base_path") or "").strip()
    public_url = str(block.get("public_url") or "").strip()
    tls_cert = str(block.get("tls_cert") or "").strip()
    tls_key = str(block.get("tls_key") or "").strip()
    trust = bool(block.get("trust_forwarded") or block.get("trust_proxy"))
    return NetworkSettings(
        host=host,
        port=port,
        base_path=base_path,
        public_url=public_url,
        tls_cert=tls_cert,
        tls_key=tls_key,
        trust_forwarded=trust,
    )


def _parse_http(block: dict) -> HttpSettings:
    compress = str(block.get("compress") or "gzip").strip().lower()
    if compress not in VALID_COMPRESS:
        raise ConfigProblem(f"[http].compress must be one of {sorted(VALID_COMPRESS)}.")
    queue = _int(block.get("request_queue_size"), 128, 8, 10_000)
    return HttpSettings(compress=compress, request_queue_size=queue)


def _parse_images(block: dict) -> ImageDeliverySettings:
    fmt = str(block.get("format") or "original").strip().lower()
    if fmt not in VALID_IMAGE_FORMAT:
        raise ConfigProblem(f"[images].format must be one of {sorted(VALID_IMAGE_FORMAT)}.")
    hw = str(block.get("hw_accel") or "auto").strip().lower()
    if hw not in VALID_HW:
        raise ConfigProblem(f"[images].hw_accel must be one of {sorted(VALID_HW)}.")
    return ImageDeliverySettings(
        transcode=bool(block.get("transcode")),
        format=fmt,
        max_edge=_int(block.get("max_edge"), 2048, 64, 8192),
        quality=_int(block.get("quality"), 85, 1, 100),
        min_bytes=_int(block.get("min_bytes"), 512_000, 0, 500_000_000),
        min_edge=_int(block.get("min_edge"), 1280, 0, 8192),
        hw_accel=hw,
    )


def _int(raw: Any, default: int, low: int, high: int) -> int:
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ConfigProblem("Expected an integer.") from None
    if value < low or value > high:
        raise ConfigProblem(f"Integer must be between {low} and {high}.")
    return value


def merge_server_patch(current: ServerSettings, patch: dict) -> ServerSettings:
    """Validate and merge a partial server settings object from the admin API."""
    if not isinstance(patch, dict):
        raise ConfigProblem("Send a server settings object.")
    net = dict(current.network.public_dict())
    http = dict(current.http.public_dict())
    images = dict(current.images.public_dict())
    if "network" in patch:
        if not isinstance(patch["network"], dict):
            raise ConfigProblem("network must be an object.")
        net.update(patch["network"])
    if "http" in patch:
        if not isinstance(patch["http"], dict):
            raise ConfigProblem("http must be an object.")
        http.update(patch["http"])
    if "images" in patch:
        if not isinstance(patch["images"], dict):
            raise ConfigProblem("images must be an object.")
        images.update(patch["images"])
    return parse_server_settings({"network": net, "http": http, "images": images})


def network_restart_required(
    saved: NetworkSettings,
    running_host: str,
    running_port: int,
    running_base: str,
) -> bool:
    if saved.host != running_host:
        return True
    if saved.port != running_port:
        return True
    if (saved.base_path or "") != (running_base or ""):
        return True
    if saved.tls_cert or saved.tls_key:
        return True
    return False


def server_toml_lines(settings: ServerSettings) -> list[str]:
    n = settings.network
    h = settings.http
    im = settings.images
    lines = [
        "[network]",
        f'host = "{_toml_str(n.host)}"',
        f"port = {n.port}",
    ]
    if n.base_path:
        lines.append(f'base_path = "{_toml_str(n.base_path)}"')
    if n.public_url:
        lines.append(f'public_url = "{_toml_str(n.public_url)}"')
    if n.tls_cert:
        lines.append(f'tls_cert = "{_toml_str(n.tls_cert)}"')
    if n.tls_key:
        lines.append(f'tls_key = "{_toml_str(n.tls_key)}"')
    if n.trust_forwarded:
        lines.append("trust_forwarded = true")
    lines.extend(
        [
            "",
            "[http]",
            f'compress = "{_toml_str(h.compress)}"',
            "",
            "[images]",
            f"transcode = {'true' if im.transcode else 'false'}",
            f'format = "{_toml_str(im.format)}"',
            f"max_edge = {im.max_edge}",
            f"quality = {im.quality}",
            f"min_bytes = {im.min_bytes}",
            f"min_edge = {im.min_edge}",
            f'hw_accel = "{_toml_str(im.hw_accel)}"',
            "",
        ]
    )
    return lines


def deck_image_override(deck_options: dict) -> ImageDeliverySettings | None:
    block = deck_options.get("images")
    if not isinstance(block, dict):
        return None
    base = ImageDeliverySettings()
    merged = dict(base.public_dict())
    merged.update(block)
    return parse_server_settings({"images": merged}).images
