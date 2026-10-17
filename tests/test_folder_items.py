# SPDX-License-Identifier: AGPL-3.0-only

import tempfile
import unittest
from pathlib import Path

from choice.folder_deck import items_from_folder_scan, parse_folder_options
from choice.folder_items import folder_item_from_path


class FolderItemsTests(unittest.TestCase):
    def test_heic_body_matches_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.heic").write_bytes(b"x")
            scan = parse_folder_options({"type": "images"})
            items = items_from_folder_scan(root, root, scan)
            one = folder_item_from_path("a.heic", root / "a.heic")
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].kind, one.kind)
            self.assertEqual(items[0].body, one.body)
