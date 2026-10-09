# SPDX-License-Identifier: AGPL-3.0-only

import json
import os
import statistics
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from choice.act import _read_log
from choice.folder_index import load_index, scan_incremental
from choice.httpd import ChoiceSite
from choice.open import open_config
from choice.work_queue import snapshot_for, wait_idle


def _build_tree(root: Path, file_count: int, dir_count: int) -> None:
    root.mkdir(parents=True, exist_ok=True)
    per = max(1, file_count // dir_count)
    n = 0
    for d in range(dir_count):
        sub = root / f"batch{d:03d}"
        sub.mkdir(parents=True, exist_ok=True)
        for _ in range(per):
            if n >= file_count:
                return
            (sub / f"f{n:06d}.jpg").write_bytes(b"x")
            n += 1


class _Response:
    def __init__(self, status: int, body: str):
        self.status = status
        self.body = body


class AsyncDecideLoadTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop("CHOICE_SYNC_WORK", None)
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()
        os.environ.setdefault("CHOICE_SYNC_WORK", "1")

    def test_async_decide_load_and_undo(self):
        root = self.tmp / "photos"
        _build_tree(root, 20000, 100)
        cfg = self.tmp / "choice.toml"
        cfg.write_text(
            f"""
[state]
dir = "state"

[[sources]]
id = "f"
type = "folder"
path = "{root.as_posix()}"

[[decks]]
id = "load"
title = "Load"
source = "f"
mount = "."
type = "images"
recursive = true
output = "sort"
sort_right = "keep"
sort_left = "bin"
""".strip(),
            encoding="utf-8",
        )
        deck = open_config(cfg).decks[0]
        scan_incremental(deck)
        ordered = list(load_index(deck.state_dir).ordered)
        self.assertGreaterEqual(len(ordered), 20000)

        ChoiceSite.allow_reuse_address = True
        server = ChoiceSite(("127.0.0.1", 0), self.tmp, config_path=cfg)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        deck_id = deck.id
        latencies: list[float] = []
        cursor = 0
        interval = 0.25
        end = time.monotonic() + 60.0
        try:
            while time.monotonic() < end:
                item_id = ordered[cursor]
                cursor += 1
                t0 = time.perf_counter()
                res = self._post(
                    port,
                    f"/api/decks/{deck_id}/decide",
                    {"item": item_id, "direction": "right"},
                )
                latencies.append(time.perf_counter() - t0)
                self.assertEqual(res.status, 200, res.body)
                body = json.loads(res.body)
                self.assertTrue(body.get("ok"), body)
                time.sleep(max(0, interval - latencies[-1]))

            p95 = statistics.quantiles(latencies, n=20)[-1]
            p50 = statistics.median(latencies)
            print(
                f"async decide load: n={len(latencies)} "
                f"p50={p50 * 1000:.2f}ms p95={p95 * 1000:.2f}ms max={max(latencies) * 1000:.2f}ms"
            )
            self.assertLessEqual(p95, 0.030, f"decide p95 {p95 * 1000:.1f} ms")

            before_id = ordered[cursor]
            cursor += 1
            res = self._post(
                port,
                f"/api/decks/{deck_id}/decide",
                {"item": before_id, "direction": "right"},
            )
            self.assertEqual(res.status, 200, res.body)
            undone = self._post(port, f"/api/decks/{deck_id}/undo", {})
            self.assertEqual(undone.status, 200, undone.body)
            self.assertTrue((root / before_id).is_file())

            after_id = ordered[cursor]
            cursor += 1
            res = self._post(
                port,
                f"/api/decks/{deck_id}/decide",
                {"item": after_id, "direction": "right"},
            )
            self.assertEqual(res.status, 200, res.body)
            self.assertTrue(
                wait_idle(deck.state_dir, timeout=120.0),
                "queue did not drain",
            )
            self.assertEqual(snapshot_for(deck).pending, 0)
            self.assertEqual(snapshot_for(deck).running, 0)
            keep_path = root / "keep" / Path(after_id).name
            if not keep_path.is_file():
                keep_path = root / "keep" / after_id
            self.assertTrue(keep_path.is_file(), f"missing {keep_path}")
            undone2 = self._post(port, f"/api/decks/{deck_id}/undo", {})
            self.assertEqual(undone2.status, 200, undone2.body)
            self.assertTrue(wait_idle(deck.state_dir, timeout=60.0))
            self.assertTrue((root / after_id).is_file())

            self.assertTrue(
                wait_idle(deck.state_dir, timeout=120.0),
                "queue did not drain after undo tests",
            )
            self._assert_files_match_log(deck, root)
        finally:
            server.shutdown()
            server.server_close()

    def _assert_files_match_log(self, deck, root: Path) -> None:
        undone = {row.get("ref") for row in _read_log(deck) if row.get("type") == "undo"}
        for row in _read_log(deck):
            if row.get("type") != "decision" or row.get("id") in undone:
                continue
            if row.get("later"):
                continue
            op = row.get("file_op")
            if not op:
                continue
            src = root / str(op.get("from") or "")
            dest = root / str(op.get("to") or "")
            self.assertFalse(src.is_file(), f"still at source {src}")
            self.assertTrue(dest.is_file(), f"missing dest {dest}")

    def _post(self, port: int, path: str, body: dict) -> _Response:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                return _Response(res.status, res.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return _Response(exc.code, exc.read().decode("utf-8"))
