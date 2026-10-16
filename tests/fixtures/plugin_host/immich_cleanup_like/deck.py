"""Immich-style image cleanup: pass/fail on photos, no directions on the plugin."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
_IMG = HERE / "sample.png"

_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f"
    b"\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _ensure_img():
    if not _IMG.is_file():
        _IMG.write_bytes(_PNG)


class Deck:
    id = "immich_cleanup_like"
    title = "Immich cleanup (fixture)"

    def list_items(self, filter=None):
        _ensure_img()
        return [
            {
                "id": "photo-1",
                "kind": "image",
                "title": "Candidate 1",
                "image_path": str(_IMG),
            },
            {
                "id": "photo-2",
                "kind": "image",
                "title": "Candidate 2",
                "image_path": str(_IMG),
            },
        ]

    def handle(self, item_id, direction, note=None):
        return {"ok": True}

    def media_bytes(self, row, n=None, side=None, item=None, index=None):
        return _PNG, "image/png"
