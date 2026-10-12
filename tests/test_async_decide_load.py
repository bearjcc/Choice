# SPDX-License-Identifier: AGPL-3.0-only

import json
import os
import statistics
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from choice.act import _read_log, index_summary
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
    def __init__(self, status: int, body: str, headers: dict | None = None):
        self.status = status
        self.body = body
        self.headers = headers or {}


class AsyncDecideLoadTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop("CHOICE_SYNC_WORK", None)
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()
        os.environ.setdefault("CHOICE_SYNC_WORK", "1")

    def test_async_decide_load_media_and_undo(self):
        root = self.tmp / "photos"
        _build_tree(root, 30000, 140)
        for name in ("keep", "reject", "like", "love", "dislike"):
            (root / name).mkdir(exist_ok=True)
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
sort_left = "reject"
sort_up = "like"
sort_down = "love"
counts = "on"
""".strip(),
            encoding="utf-8",
        )
        deck = open_config(cfg).decks[0]
        scan_incremental(deck)
        ordered = list(load_index(deck.state_dir).ordered)
        self.assertGreaterEqual(len(ordered), 29900)

        growth_dir = root / "batch139"
        stop = threading.Event()

        def _grow():
            i = 0
            while not stop.is_set():
                (growth_dir / f"g{i:06d}.jpg").write_bytes(b"y")
                i += 1
                time.sleep(0.004)

        grow = threading.Thread(target=_grow, daemon=True)
        grow.start()

        ChoiceSite.allow_reuse_address = True
        server = ChoiceSite(("127.0.0.1", 0), self.tmp, config_path=cfg)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        deck_id = deck.id
        decide_lat: list[float] = []
        etag = ""
        media_id = ordered[500]
        cursor = 0
        interval = 0.25
        end = time.monotonic() + 60.0
        undo_failures = 0
        try:
            path = (
                f"/api/decks/{deck_id}/media?item={urllib.parse.quote(media_id)}"
                "&w=1280&v=1"
            )
            cold_ms = None
            for _ in range(10):
                t0 = time.perf_counter()
                res = self._get_raw(port, path)
                elapsed = time.perf_counter() - t0
                if res.status == 200:
                    if cold_ms is None:
                        cold_ms = elapsed
                    etag = res.headers.get("ETag") or res.headers.get("etag") or ""
                    if etag:
                        break
            self.assertTrue(etag, "expected warm media ETag")
            self.assertIsNotNone(cold_ms)
            self.assertLess(cold_ms, 0.30, f"cold media {cold_ms*1000:.0f}ms")

            while time.monotonic() < end:
                item_id = ordered[cursor]
                cursor += 1
                t0 = time.perf_counter()
                res = self._post(
                    port,
                    f"/api/decks/{deck_id}/decide",
                    {"item": item_id, "direction": "right"},
                )
                decide_lat.append(time.perf_counter() - t0)
                self.assertEqual(res.status, 200, res.body)
                self.assertTrue(json.loads(res.body).get("ok"), res.body)
                time.sleep(max(0, interval - decide_lat[-1]))

            decide_p95 = statistics.quantiles(decide_lat, n=20)[-1]
            print(
                f"decide n={len(decide_lat)} p50={statistics.median(decide_lat)*1000:.2f}ms "
                f"p95={decide_p95*1000:.2f}ms"
            )
            decide_cap = 1.0 if os.getenv("GITHUB_ACTIONS") else 0.040
            self.assertLessEqual(decide_p95, decide_cap)

            media_304: list[float] = []
            for _ in range(40):
                t0 = time.perf_counter()
                res = self._get_raw(port, path, headers={"If-None-Match": etag})
                media_304.append(time.perf_counter() - t0)
                self.assertEqual(res.status, 304, str(res.body)[:80])
            media_p95 = statistics.quantiles(media_304, n=20)[-1]
            print(f"media 304 p95={media_p95*1000:.2f}ms")
            self.assertLessEqual(media_p95, 0.030)

            self.assertTrue(wait_idle(deck.state_dir, timeout=180.0))
            self.assertEqual(snapshot_for(deck).pending, 0)

            before_id = ordered[cursor]
            cursor += 1
            self._post(
                port,
                f"/api/decks/{deck_id}/decide",
                {"item": before_id, "direction": "right"},
            )
            self._post(port, f"/api/decks/{deck_id}/undo", {})

            after_id = ordered[cursor]
            cursor += 1
            self._post(
                port,
                f"/api/decks/{deck_id}/decide",
                {"item": after_id, "direction": "right"},
            )
            self.assertTrue(wait_idle(deck.state_dir, timeout=120.0))
            for _ in range(10):
                res = self._post(port, f"/api/decks/{deck_id}/undo", {})
                if res.status != 200:
                    undo_failures += 1
            self.assertEqual(undo_failures, 0)

            self._assert_no_double_moves(deck, root)
            snap = index_summary(deck)
            self.assertTrue(snap.get("ok"))
            idx = load_index(deck.state_dir)
            self.assertEqual(snap.get("left"), snap.get("total") - snap.get("decided"))
            for rid in idx.ordered:
                self.assertFalse(rid.startswith("keep/"))
                self.assertFalse(rid.startswith("reject/"))
        finally:
            stop.set()
            grow.join(timeout=2.0)
            server.shutdown()
            server.server_close()

    def _assert_no_double_moves(self, deck, root: Path) -> None:
        seen_dest: set[str] = set()
        undone = {row.get("ref") for row in _read_log(deck) if row.get("type") == "undo"}
        for row in _read_log(deck):
            if row.get("type") != "decision" or row.get("id") in undone:
                continue
            if row.get("later"):
                continue
            op = row.get("file_op")
            if not op:
                continue
            dest = str(op.get("to") or "")
            self.assertNotIn(dest, seen_dest, f"duplicate move to {dest}")
            seen_dest.add(dest)

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
                return _Response(res.status, res.read().decode("utf-8"), dict(res.headers))
        except urllib.error.HTTPError as exc:
            return _Response(exc.code, exc.read().decode("utf-8"), dict(exc.headers))

    def _get_raw(
        self, port: int, path: str, headers: dict | None = None
    ) -> _Response:
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                return _Response(res.status, res.read(), dict(res.headers))
        except urllib.error.HTTPError as exc:
            return _Response(exc.code, exc.read(), dict(exc.headers))
