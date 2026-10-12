# SPDX-License-Identifier: AGPL-3.0-only
"""Phone-sized images for /media. Pillow is optional (see pyproject optional extra `images`)."""

from __future__ import annotations

import hashlib
import io
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path

_MAX_EDGE = 1600
_WIDTH_BUCKETS = (640, 960, 1280, 1600)
_QUALITY = 85
_CACHE_MAX_BYTES = 1536 * 2**20
_CACHE_MAX_AGE = 30 * 86400
_SWEEP_EVERY = 6 * 3600
_RESIZE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".avif": "image/avif",
}
_lock = threading.Lock()
_cache_write_guard = threading.Lock()
_cache_write_locks: dict[str, threading.Lock] = {}
_last_sweep = 0.0
_pillow_checked = False
_pillow_ok = False
_media_fmt = "webp"


@dataclass
class ServedMedia:
    path: Path | None
    data: bytes | None
    content_type: str
    etag: str
    cache_control: str = "private, max-age=86400"


def content_type(path: Path) -> str:
    return _TYPES.get(path.suffix.lower(), "application/octet-stream")


def view_path(src: Path, cache_dir: Path) -> Path:
    """Legacy helper: phone-sized file path when Pillow is installed."""
    served = prepare_file(src, cache_dir, etag_version="legacy")
    if served.path is not None:
        return served.path
    return src


def prepare_file(
    src: Path,
    cache_dir: Path,
    *,
    full: bool = False,
    max_edge: int = _MAX_EDGE,
    width: int | None = None,
    etag_version: str = "",
) -> ServedMedia:
    src = src.resolve()
    edge = _edge_limit(max_edge, width)
    try:
        stat = src.stat()
    except OSError:
        ctype = content_type(src)
        return ServedMedia(path=src, data=None, content_type=ctype, etag=_etag_weak("missing"))
    etag = _etag_file(src, stat, edge, etag_version)
    if full or not _resize_allowed(src):
        return ServedMedia(
            path=src,
            data=None,
            content_type=content_type(src),
            etag=etag,
        )
    if not _pillow_ready():
        return ServedMedia(path=src, data=None, content_type=content_type(src), etag=etag)
    key = _file_cache_key(src, stat, edge)
    cached = _cache_path(cache_dir, key)
    if cached.is_file():
        _touch(cached)
        return ServedMedia(
            path=cached,
            data=None,
            content_type=content_type(cached),
            etag=etag,
        )
    data, ctype = _encode_image_file(src, edge)
    if data is None:
        return ServedMedia(path=src, data=None, content_type=content_type(src), etag=etag)
    if len(data) >= stat.st_size and src.suffix.lower() in {".jpg", ".jpeg"}:
        return ServedMedia(path=src, data=None, content_type=content_type(src), etag=etag)
    _write_cache(cache_dir, key, data)
    return ServedMedia(path=_cache_path(cache_dir, key), data=None, content_type=ctype, etag=etag)


def prepare_bytes(
    data: bytes,
    source_type: str,
    cache_dir: Path,
    cache_identity: str,
    *,
    full: bool = False,
    max_edge: int = _MAX_EDGE,
    width: int | None = None,
    etag_version: str = "",
) -> ServedMedia:
    edge = _edge_limit(max_edge, width)
    digest = hashlib.sha256(data).hexdigest()
    etag = _etag_bytes(cache_identity, digest, edge, etag_version)
    if full or not _pillow_ready() or not _bytes_resizable(source_type, data):
        return ServedMedia(
            path=None,
            data=data,
            content_type=source_type or "application/octet-stream",
            etag=etag,
        )
    key = _bytes_cache_key(cache_identity, digest, edge)
    cached = _cache_path(cache_dir, key)
    if cached.is_file():
        _touch(cached)
        return ServedMedia(
            path=cached,
            data=None,
            content_type=content_type(cached),
            etag=etag,
        )
    out, ctype = _encode_image_bytes(data, edge)
    if out is None or len(out) >= len(data):
        return ServedMedia(
            path=None,
            data=data,
            content_type=source_type or "application/octet-stream",
            etag=etag,
        )
    _write_cache(cache_dir, key, out)
    return ServedMedia(
        path=_cache_path(cache_dir, key),
        data=None,
        content_type=ctype,
        etag=etag,
    )


def maybe_sweep(cache_dir: Path) -> None:
    global _last_sweep
    now = time.time()
    if now - _last_sweep < _SWEEP_EVERY:
        return
    with _lock:
        if now - _last_sweep < _SWEEP_EVERY:
            return
        _last_sweep = now
    sweep_cache(cache_dir)


def sweep_cache(cache_dir: Path) -> None:
    if not cache_dir.is_dir():
        return
    cut = time.time() - _CACHE_MAX_AGE
    rows: list[tuple[float, int, Path]] = []
    try:
        for entry in cache_dir.iterdir():
            if not entry.is_file() or entry.name.endswith(".tmp"):
                continue
            try:
                stat = entry.stat()
            except OSError:
                continue
            rows.append((stat.st_mtime, stat.st_size, entry))
    except OSError:
        return
    rows.sort()
    total = sum(size for _, size, _ in rows)
    for mtime, size, path in rows:
        if mtime >= cut and total <= _CACHE_MAX_BYTES:
            break
        try:
            path.unlink()
            total -= size
        except OSError:
            continue


def snap_edge(width: int | None) -> int | None:
    """Snap requested width up to a fixed bucket (or None for default max)."""
    if width is None or width <= 0:
        return None
    if width >= _MAX_EDGE:
        return _MAX_EDGE
    for bucket in _WIDTH_BUCKETS:
        if width <= bucket:
            return bucket
    return _MAX_EDGE


def edge_for_viewport(css_width: int, dpr: float = 1.0) -> int:
    raw = int(css_width * max(1.0, dpr))
    snapped = snap_edge(raw)
    return snapped or _MAX_EDGE


def _edge_limit(max_edge: int, width: int | None) -> int:
    edge = max(320, min(max_edge, _MAX_EDGE))
    if width is not None and width > 0:
        snapped = snap_edge(width)
        if snapped is not None:
            edge = min(edge, snapped)
    return edge


def _resize_allowed(path: Path) -> bool:
    ext = path.suffix.lower()
    if ext in _RESIZE_EXT:
        return True
    if ext in {".heic", ".heif", ".jxl"}:
        return _pillow_ready()
    return False


def _bytes_resizable(ctype: str, data: bytes) -> bool:
    if ctype.startswith("image/") and ctype not in {"image/svg+xml", "image/gif"}:
        return True
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return True
    if data[:2] == b"\xff\xd8":
        return True
    if data[:4] == b"RIFF" and len(data) > 12 and data[8:12] == b"WEBP":
        return True
    return False


def _pillow_ready() -> bool:
    global _pillow_checked, _pillow_ok, _media_fmt
    if _pillow_checked:
        return _pillow_ok
    with _lock:
        if _pillow_checked:
            return _pillow_ok
        _pillow_checked = True
        try:
            from PIL import Image  # noqa: F401
            from PIL import features as pf

            _pillow_ok = True
            if not pf.check("webp"):
                _media_fmt = "jpeg"
        except ImportError:
            _pillow_ok = False
        return _pillow_ok


def _file_cache_key(path: Path, stat: os.stat_result, edge: int) -> str:
    material = f"file|{path}|{stat.st_mtime_ns}|{stat.st_size}|{edge}|{_media_fmt}|{_QUALITY}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _bytes_cache_key(identity: str, digest: str, edge: int) -> str:
    material = f"bytes|{identity}|{digest}|{edge}|{_media_fmt}|{_QUALITY}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _cache_path(cache_dir: Path, key: str) -> Path:
    ext = ".webp" if _media_fmt == "webp" else ".jpg"
    return cache_dir / f"{key[:32]}{ext}"


def _cache_write_lock(cache_dir: Path, key: str) -> threading.Lock:
    token = f"{cache_dir.resolve()}|{key}"
    with _cache_write_guard:
        lock = _cache_write_locks.get(token)
        if lock is None:
            lock = threading.Lock()
            _cache_write_locks[token] = lock
        return lock


def _write_cache(cache_dir: Path, key: str, data: bytes) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = _cache_path(cache_dir, key)
    with _cache_write_lock(cache_dir, key):
        if dest.is_file():
            return
        tmp = dest.with_suffix(dest.suffix + f".{threading.get_ident()}.tmp")
        try:
            tmp.write_bytes(data)
            try:
                tmp.replace(dest)
            except OSError as exc:
                if dest.is_file() or _cache_replace_race(exc):
                    return
                raise
        finally:
            tmp.unlink(missing_ok=True)
    maybe_sweep(cache_dir)


def _cache_replace_race(exc: OSError) -> bool:
    code = getattr(exc, "winerror", None)
    if code is None:
        code = exc.errno
    return code in {5, 13, 17, 32}


def _touch(path: Path) -> None:
    try:
        if time.time() - path.stat().st_mtime > 86400:
            path.touch()
    except OSError:
        return


def _register_optional_codecs() -> None:
    from choice.optional_codecs import register_optional_codecs

    register_optional_codecs()


def _encode_image_file(path: Path, edge: int) -> tuple[bytes | None, str]:
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return None, ""
    _register_optional_codecs()
    try:
        from choice.source_reads import hold_source_read

        with hold_source_read(path):
            with Image.open(path) as image:
                image = ImageOps.exif_transpose(image)
                image.thumbnail((edge, edge))
                image = _flatten(image)
                return _save_image(image)
    except Exception:
        return None, ""


def _encode_image_bytes(data: bytes, edge: int) -> tuple[bytes | None, str]:
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return None, ""
    try:
        with Image.open(io.BytesIO(data)) as image:
            image = ImageOps.exif_transpose(image)
            image.thumbnail((edge, edge))
            image = _flatten(image)
            return _save_image(image)
    except Exception:
        return None, ""


def _flatten(image):
    from PIL import Image

    if image.mode in {"RGB", "L"}:
        return image
    if image.mode == "RGBA":
        bg = Image.new("RGB", image.size, (20, 22, 28))
        bg.paste(image, mask=image.split()[-1])
        return bg
    return image.convert("RGB")


def _save_image(image) -> tuple[bytes, str]:
    buf = io.BytesIO()
    if _media_fmt == "webp":
        image.save(buf, "WEBP", quality=_QUALITY, method=4)
        return buf.getvalue(), "image/webp"
    image.save(buf, "JPEG", quality=_QUALITY, optimize=True, progressive=True)
    return buf.getvalue(), "image/jpeg"


def _etag_file(path: Path, stat: os.stat_result, edge: int, version: str) -> str:
    material = f"{path}|{stat.st_mtime_ns}|{stat.st_size}|{edge}|{version}"
    return f'"{hashlib.sha256(material.encode()).hexdigest()[:24]}"'


def _etag_bytes(identity: str, digest: str, edge: int, version: str) -> str:
    material = f"{identity}|{digest}|{edge}|{version}"
    return f'"{hashlib.sha256(material.encode()).hexdigest()[:24]}"'


def _etag_weak(label: str) -> str:
    return f'"{hashlib.sha256(label.encode()).hexdigest()[:16]}"'
