# SPDX-License-Identifier: AGPL-3.0-only

import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from choice.deck_cache import load_items as cached_load_items
from choice.deck_index import clear_index
from choice.open import open_config

FIX = Path(__file__).resolve().parent / "fixtures" / "plugin_host"
_COUNTS = "list_counts.json"


class PluginListCountsAtomicTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _config(self, mount: str = "big_list_8k") -> Path:
        cfg = self.tmp / "choice.toml"
        cfg.write_text(
            f"""
[state]
dir = "state"

[[sources]]
id = "swipe"
type = "swipe"
path = "{FIX.as_posix()}"

[[decks]]
id = "d"
title = "D"
source = "swipe"
mount = "{mount}"
""".strip(),
            encoding="utf-8",
        )
        return cfg

    def test_list_counts_written_at_most_once_per_load(self):
        opened = open_config(self._config())
        deck = opened.decks[0]
        clear_index(deck)
        counts_path = deck.state_dir / _COUNTS
        writes: list[int] = []
        import choice.atomic_io as atomic_io

        real = atomic_io.write_json_atomic

        def counting(path, payload, **kwargs):
            if path.name == _COUNTS:
                writes.append(1)
            return real(path, payload, **kwargs)

        with mock.patch.object(atomic_io, "write_json_atomic", counting):
            items, _ = deck.load_items()
        self.assertGreaterEqual(len(items), 8000)
        self.assertLessEqual(len(writes), 1, f"expected one persist, got {len(writes)}")

        writes.clear()
        with mock.patch.object(atomic_io, "write_json_atomic", counting):
            items2, _ = cached_load_items(deck)
        self.assertEqual(len(items2), len(items))
        self.assertLessEqual(len(writes), 1)

    def test_concurrent_reader_never_sees_partial_json(self):
        opened = open_config(self._config())
        deck = opened.decks[0]
        clear_index(deck)
        counts_path = deck.state_dir / _COUNTS
        errors: list[str] = []
        stop = threading.Event()

        def reader():
            while not stop.is_set():
                if not counts_path.is_file():
                    time.sleep(0.0005)
                    continue
                try:
                    raw = counts_path.read_text(encoding="utf-8")
                    if not raw.strip():
                        errors.append("empty file")
                        continue
                    data = json.loads(raw)
                    if not isinstance(data.get("order"), list):
                        errors.append("bad shape")
                except json.JSONDecodeError as exc:
                    errors.append(f"json: {exc}")
                time.sleep(0.0002)

        t = threading.Thread(target=reader, daemon=True)
        t.start()
        try:
            deck.load_items()
        finally:
            stop.set()
            t.join(timeout=2)
        self.assertEqual(errors, [])

    def test_first_items_load_8k_under_choice_overhead_budget(self):
        os.environ["CHOICE_DISABLE_WARM"] = "1"
        opened = open_config(self._config())
        deck = opened.decks[0]
        clear_index(deck)
        start = time.perf_counter()
        items, _ = cached_load_items(deck)
        elapsed = time.perf_counter() - start
        os.environ.pop("CHOICE_DISABLE_WARM", None)
        self.assertGreaterEqual(len(items), 8000)
        budget = 0.45 if sys.platform == "win32" else 0.3
        self.assertLess(
            elapsed,
            budget,
            f"Choice overhead for 8k plugin load was {elapsed:.3f}s",
        )


if __name__ == "__main__":
    unittest.main()
