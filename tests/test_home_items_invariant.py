# SPDX-License-Identifier: AGPL-3.0-only

import json
import os
import tempfile
import unittest
from pathlib import Path

from choice.act import index_summary, progress
from choice.deck_index import clear_index, record_items
from choice.folder_index import scan_incremental
from choice.load import resolve
from choice.open import open_config


class HomeItemsInvariantTests(unittest.TestCase):
    def _assert_match(self, deck) -> None:
        home = index_summary(deck)
        self.assertTrue(home.get("ok"))
        items = progress(deck, pending=True, limit=200)
        self.assertTrue(items.get("ok"))
        for key in ("total", "decided", "left"):
            self.assertEqual(
                home.get(key),
                items.get(key),
                msg=f"{deck.id} {key} home={home.get(key)} items={items.get(key)}",
            )
        self.assertEqual(home["total"], home["decided"] + home["left"])

    def test_folder_sort_deck_fully_decided(self):
        with tempfile.TemporaryDirectory() as tmpname:
            tmp = Path(tmpname)
            (tmp / "deck.json").write_text(
                json.dumps(
                    {
                        "source": {
                            "type": "images",
                            "path": ".",
                            "recursive": True,
                            "output": "sort",
                            "sort": {"right": "keep", "left": "reject"},
                        },
                        "directions": {
                            "right": {"label": "Keep", "value": "keep"},
                            "left": {"label": "Reject", "value": "reject"},
                        },
                    }
                ),
                encoding="utf-8",
            )
            for name in ("keep", "reject", "incoming"):
                (tmp / name).mkdir()
            (tmp / "incoming" / "a.jpg").write_bytes(b"x")
            deck = resolve(tmp).decks[0]
            scan_incremental(deck)
            from choice.act import decide

            decide(deck, "incoming/a.jpg", "right", None)
            scan_incremental(deck)
            snap = progress(deck, pending=True, limit=200)
            self.assertFalse(snap.get("scanning"))
            self.assertEqual(snap["left"], 0)
            self.assertGreater(snap["decided"], 0)
            self.assertEqual(snap["total"], snap["decided"])
            self.assertEqual(f"{snap['decided']} decided.", f"{snap['decided']} decided.")
            self._assert_match(deck)
            home = index_summary(deck)
            self.assertEqual(home["left"], 0)
            self.assertFalse(home.get("stale") and home.get("left") == home.get("total"))

    def test_folder_view_filter_matches_home(self):
        with tempfile.TemporaryDirectory() as tmpname:
            tmp = Path(tmpname)
            for i in range(10):
                (tmp / f"p{i}.jpg").write_bytes(b"x")
            (tmp / "deck.json").write_text(
                json.dumps(
                    {
                        "source": {"type": "images", "path": ".", "recursive": False},
                        "directions": {"right": {"label": "Yes", "value": "yes"}},
                        "view": {
                            "sort_mode": "filename",
                            "file_types": ["png"],
                        },
                    }
                ),
                encoding="utf-8",
            )
            deck = resolve(tmp).decks[0]
            scan_incremental(deck)
            self._assert_match(deck)

    def test_plugin_hides_decided(self):
        os.environ["CHOICE_DISABLE_WARM"] = "1"
        try:
            fix = Path(__file__).resolve().parent / "fixtures" / "plugin_host"
            cfg = tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False)
            cfg.write(
                f"""
[state]
dir = "state"

[[sources]]
id = "swipe"
type = "swipe"
path = "{fix.as_posix()}"

[[decks]]
id = "d"
title = "D"
source = "swipe"
mount = "hides_decided"
""".strip()
            )
            cfg.flush()
            deck = open_config(Path(cfg.name)).decks[0]
            gone = [
                f'{{"type":"decision","id":"{i}","item":"gone-{i}","value":"right","later":false}}'
                for i in range(5)
            ]
            log = deck.state_dir / "decisions.jsonl"
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text("\n".join(gone) + "\n", encoding="utf-8")
            items, _ = deck.load_items()
            record_items(deck, items)
            clear_index(deck)
            self._assert_match(deck)
        finally:
            os.environ.pop("CHOICE_DISABLE_WARM", None)

    def test_offset_paging_past_first_chunk(self):
        with tempfile.TemporaryDirectory() as tmpname:
            tmp = Path(tmpname)
            for i in range(250):
                (tmp / f"f{i:03d}.jpg").write_bytes(b"x")
            (tmp / "deck.json").write_text(
                json.dumps(
                    {
                        "source": {
                            "type": "images",
                            "path": ".",
                            "recursive": True,
                            "output": "results",
                        },
                        "directions": {"right": {"label": "Yes", "value": "yes"}},
                    }
                ),
                encoding="utf-8",
            )
            deck = resolve(tmp).decks[0]
            self.assertIsNotNone(deck.folder_scan)
            scan_incremental(deck)
            p1 = progress(deck, pending=True, limit=200, offset=0)
            self.assertEqual(len(p1["items"]), 200)
            self.assertEqual(p1.get("next_offset"), 200)
            p2 = progress(deck, pending=True, limit=200, offset=200)
            self.assertEqual(len(p2["items"]), 50)
            self.assertNotIn("next_offset", p2)
