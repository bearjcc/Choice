# SPDX-License-Identifier: AGPL-3.0-only
"""Register optional Pillow codecs when their packages are installed."""

from __future__ import annotations


def register_optional_codecs() -> None:
    try:
        import pillow_heif  # type: ignore[import-not-found]

        pillow_heif.register_heif_opener()
    except Exception:
        pass
    try:
        import pillow_jxl  # type: ignore[import-not-found]  # noqa: F401

        register = getattr(pillow_jxl, "register_jxl_opener", None)
        if callable(register):
            register()
    except Exception:
        pass
