from pathlib import Path

HERE = Path(__file__).resolve().parent
_IMG = HERE / "side.png"
_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f"
    b"\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


class Deck:
    id = "pair_audit"
    title = "Pair audit"
    directions = {
        "left": {"label": "A", "value": "A"},
        "right": {"label": "B", "value": "B"},
    }

    def list_items(self, filter=None):
        if not _IMG.is_file():
            _IMG.write_bytes(_PNG)
        return [
            {
                "id": "text-pair",
                "title": "Text pair",
                "body": "Should not duplicate A",
                "sections": [{"title": "Hint", "text": "Pick the shorter answer"}],
                "ab": {
                    "a": {"label": "A", "text": "Yes"},
                    "b": {"label": "B", "text": "No, because reasons"},
                },
            },
            {
                "id": "image-pair",
                "title": "Image pair",
                "sections": [{"title": "Context", "text": "Same photo both sides"}],
                "ab": {
                    "a": {"label": "A", "image": str(_IMG)},
                    "b": {"label": "B", "image": str(_IMG)},
                },
            },
        ]

    def handle(self, item_id, direction, note=None):
        return {"ok": True}

    def media_bytes(self, row, n=None, side=None, item=None, index=None):
        return _PNG, "image/png"
