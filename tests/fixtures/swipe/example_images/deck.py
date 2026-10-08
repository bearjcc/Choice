"""Example image deck: proves kind=image, media serving, a destructive action with undo.

Images: ./images/*.png (generate dummies with: python make_dummies.py).
left  = Trash (destructive): moves the file into state trash with an undo token; undo restores it.
right = Keep, down = Skip: record only (no side effects).
"""

import os
import shutil
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
IMAGES = os.environ.get("EXAMPLE_IMAGES_DIR", os.path.join(HERE, "images"))
TRASH = os.environ.get(
    "EXAMPLE_IMAGES_TRASH", os.path.join(HERE, "..", "..", "state", "trash", "example_images")
)
EXT = (".png", ".jpg", ".jpeg", ".webp")


class Deck:
    id = "example_images"
    title = "Example images (dummy)"
    directions = {
        "right": {"label": "Keep", "color": "#1f9d55", "destructive": False},
        "left": {"label": "Trash", "color": "#d64545", "destructive": True},
        "down": {"label": "Skip", "color": "#56607a", "destructive": False},
    }

    def filters(self):
        return [{"name": "big_only", "label": "Only files > 20 KB", "type": "bool"}]

    def _path(self, item_id):
        name = os.path.basename(item_id)  # ids are bare file names inside IMAGES only
        p = os.path.join(IMAGES, name)
        return p if name == item_id and os.path.isfile(p) else None

    def list_items(self, filter=None):
        f = filter or {}
        out = []
        if not os.path.isdir(IMAGES):
            return out
        for name in sorted(os.listdir(IMAGES)):
            p = os.path.join(IMAGES, name)
            if not name.lower().endswith(EXT) or not os.path.isfile(p):
                continue
            size = os.path.getsize(p)
            if f.get("big_only") and size <= 20 * 1024:
                continue
            out.append(
                {
                    "id": name,
                    "kind": "image",
                    "title": name,
                    "body": "Dummy test image.",
                    "fields": {"size": f"{size // 1024} KB"},
                    "image_path": p,
                    "default_label": None,
                }
            )
        return out

    def handle(self, item_id, direction):
        p = self._path(item_id)
        if p is None:
            return {"ok": False, "message": "file is gone"}
        if direction == "left":
            token = uuid.uuid4().hex
            dest = os.path.join(TRASH, token)
            os.makedirs(dest, exist_ok=True)
            shutil.move(p, os.path.join(dest, item_id))
            return {"ok": True, "undo_token": token, "message": f"Moved {item_id} to trash"}
        return {
            "ok": True,
            "undo_token": None,
            "message": {"right": "Kept", "down": "Skipped"}.get(direction, "ok"),
        }

    def undo(self, item_id, undo_token):
        if not undo_token:
            return {"ok": True, "message": "Undone"}  # keep/skip had no side effects
        src = os.path.join(TRASH, os.path.basename(str(undo_token)), os.path.basename(item_id))
        dst = os.path.join(IMAGES, os.path.basename(item_id))
        if not os.path.isfile(src):
            return {"ok": False, "message": "not in trash any more"}
        if os.path.exists(dst):
            return {"ok": False, "message": "a file with that name is back already"}
        shutil.move(src, dst)
        try:
            os.rmdir(os.path.dirname(src))
        except OSError:
            pass
        return {"ok": True, "message": f"Restored {item_id}"}
