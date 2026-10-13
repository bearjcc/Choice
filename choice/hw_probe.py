# SPDX-License-Identifier: AGPL-3.0-only
"""Optional accelerated image paths (no hard dependencies)."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import Any


@dataclass
class HwAccelStatus:
    pillow: bool
    ffmpeg: bool
    ffmpeg_hw: list[str]
    vips: bool
    selected: str
    note: str

    def public(self) -> dict[str, Any]:
        return {
            "pillow": self.pillow,
            "ffmpeg": self.ffmpeg,
            "ffmpeg_hw": self.ffmpeg_hw,
            "vips": self.vips,
            "selected": self.selected,
            "note": self.note,
        }


def probe_codecs() -> dict[str, bool]:
    out = {"webp": False, "avif": False, "jxl": False}
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        return out
    out["webp"] = True
    try:
        import pillow_heif  # noqa: F401

        out["avif"] = True
    except ImportError:
        pass
    try:
        import pillow_jxl  # noqa: F401

        out["jxl"] = True
    except ImportError:
        pass
    return out


def probe_hw_accel(requested: str = "auto") -> HwAccelStatus:
    pillow = False
    try:
        from PIL import Image  # noqa: F401

        pillow = True
    except ImportError:
        pass
    ffmpeg = shutil.which("ffmpeg") is not None
    ffmpeg_hw: list[str] = []
    if ffmpeg:
        try:
            proc = subprocess.run(
                ["ffmpeg", "-hide_banner", "-hwaccels"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            for line in (proc.stdout or "").splitlines():
                name = line.strip().lower()
                if name in {"vaapi", "qsv", "nvenc", "cuda", "dxva2", "videotoolbox"}:
                    ffmpeg_hw.append(name)
        except (OSError, subprocess.TimeoutExpired):
            ffmpeg_hw = []
    vips = shutil.which("vips") is not None or shutil.which("vipsthumbnail") is not None
    selected = "pillow"
    note = "Pillow resize/encode runs on the CPU."
    req = (requested or "auto").lower()
    if req == "off":
        selected = "pillow"
    elif req == "ffmpeg" and ffmpeg:
        selected = "ffmpeg"
        note = "ffmpeg CLI may use hardware encoders when configured; Choice still shells out per job."
    elif req == "vips" and vips:
        selected = "vips"
        note = "libvips uses a thread pool on the CPU; some builds link OpenJPEG/HEIF accelerators."
    elif req == "auto":
        if vips:
            selected = "vips"
            note = "libvips auto-selected when available; otherwise Pillow on CPU."
        elif ffmpeg:
            selected = "ffmpeg"
            note = "ffmpeg auto-selected for transcode experiments; Pillow remains the default serve path."
    if req in {"ffmpeg", "vips"} and selected not in {req, "pillow"}:
        note = f"Requested {req} is not installed; using Pillow on CPU."
        selected = "pillow"
    return HwAccelStatus(
        pillow=pillow,
        ffmpeg=ffmpeg,
        ffmpeg_hw=ffmpeg_hw,
        vips=vips,
        selected=selected,
        note=note,
    )
