# SPDX-License-Identifier: AGPL-3.0-only
"""Transcode-on-serve with on-disk variant cache."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from choice.media import ServedMedia, prepare_file
from choice.server_settings import ImageDeliverySettings


def _profile_key(profile: ImageDeliverySettings) -> str:
    payload = json.dumps(profile.public_dict(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _source_key(src: Path) -> str:
    stat = src.stat()
    return f"{stat.st_mtime_ns}:{stat.st_size}"


def should_transcode(src: Path, profile: ImageDeliverySettings) -> bool:
    if not profile.transcode or profile.format == "original":
        return False
    try:
        stat = src.stat()
    except OSError:
        return False
    if profile.min_bytes and stat.st_size < profile.min_bytes:
        return False
    return True


def variant_cache_path(cache_dir: Path, src: Path, profile: ImageDeliverySettings) -> Path:
    digest = hashlib.sha256(
        f"{src.resolve()}|{_source_key(src)}|{_profile_key(profile)}".encode()
    ).hexdigest()
    ext = profile.format if profile.format != "original" else "bin"
    return cache_dir / "variants" / f"{digest}.{ext}"


def serve_with_delivery(
    src: Path,
    cache_dir: Path,
    profile: ImageDeliverySettings,
    *,
    full: bool = False,
    width: int | None = None,
    etag_version: str = "",
) -> ServedMedia:
    """Serve original or a cached transcode variant."""
    if full or not should_transcode(src, profile):
        return prepare_file(
            src,
            cache_dir,
            full=full,
            max_edge=profile.max_edge,
            width=width,
            etag_version=etag_version,
        )
    variant = variant_cache_path(cache_dir, src, profile)
    if variant.is_file():
        from choice.media import content_type

        return ServedMedia(
            path=variant,
            data=None,
            content_type=content_type(variant),
            etag=etag_version or _source_key(src),
        )
    base = prepare_file(
        src,
        cache_dir,
        full=False,
        max_edge=profile.max_edge,
        width=width,
        etag_version=etag_version,
    )
    if base.path is None or profile.format == "webp":
        return base
    encoded = _encode_format(base.path, profile)
    if encoded is None:
        return base
    variant.parent.mkdir(parents=True, exist_ok=True)
    variant.write_bytes(encoded)
    from choice.media import content_type

    return ServedMedia(
        path=variant,
        data=None,
        content_type=content_type(variant),
        etag=etag_version or _source_key(src),
    )


def _encode_format(src: Path, profile: ImageDeliverySettings) -> bytes | None:
    try:
        from PIL import Image
    except ImportError:
        return None
    fmt = profile.format.upper()
    if fmt == "JXL":
        fmt = "JPEGXL"
    try:
        with Image.open(src) as im:
            im = im.convert("RGB")
            buf = __import__("io").BytesIO()
            save_kw = {"quality": profile.quality}
            if fmt in {"WEBP", "AVIF", "JPEGXL"}:
                im.save(buf, format=fmt, **save_kw)
            else:
                return None
            return buf.getvalue()
    except Exception:
        return None


def preview_transcode(src: Path, profile: ImageDeliverySettings) -> dict:
    try:
        orig = src.stat().st_size
    except OSError as exc:
        return {"ok": False, "message": str(exc)}
    served = serve_with_delivery(src, src.parent / ".choice-transcode-preview", profile)
    if served.path is None:
        return {"ok": False, "message": "Could not transcode sample."}
    try:
        out = served.path.stat().st_size
    except OSError:
        out = 0
    return {
        "ok": True,
        "original_bytes": orig,
        "output_bytes": out,
        "format": profile.format,
        "path": str(served.path),
    }
