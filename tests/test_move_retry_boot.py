# SPDX-License-Identifier: AGPL-3.0-only

import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from choice.load import resolve
from choice.source_reads import hold_source_read
from choice.work_queue import (
    WorkJob,
    _save_jobs,
    boot_deck,
    drop_memory_state,
    wait_idle,
)


def _sort_deck(tmp: Path):
    (tmp / "deck.json").write_text(
        json.dumps(
            {
                "source": {
                    "type": "images",
                    "path": ".",
                    "recursive": True,
                    "output": "sort",
                    "sort": {"right": "keep"},
                },
                "directions": {"right": {"label": "Keep", "value": "keep"}},
            }
        ),
        encoding="utf-8",
    )
    src = tmp / "card.jpg"
    src.write_bytes(b"jpeg-bytes")
    (tmp / "keep").mkdir()
    opened = resolve(tmp)
    deck = opened.decks[0]
    deck.actor = "tester"
    return deck


class MoveRetryBootTests(unittest.TestCase):
    def test_failed_job_with_source_revived_at_boot(self):
        with tempfile.TemporaryDirectory() as tmpname:
            tmp = Path(tmpname)
            deck = _sort_deck(tmp)
            src = tmp / "card.jpg"
            op = {"op": "move", "from": "card.jpg", "to": "keep/card.jpg"}
            job = WorkJob(
                id="j1",
                decision_id="dec-1",
                kind="file",
                status="failed",
                attempts=12,
                last_error="WinError 32",
                file_op=op,
                deck_id=deck.id,
                deck_root=str(tmp),
                state_dir=str(deck.state_dir),
            )
            os.environ["CHOICE_SYNC_WORK"] = "1"
            try:
                _save_jobs(deck.state_dir, [job])
                drop_memory_state(deck.state_dir)
                boot_deck(deck)
                wait_idle(deck.state_dir, timeout=30.0)
                self.assertFalse(src.is_file())
                self.assertTrue((tmp / "keep" / "card.jpg").is_file())
            finally:
                os.environ.pop("CHOICE_SYNC_WORK", None)

    def test_sharing_violation_retries_then_succeeds(self):
        from choice.file_moves import MoveNotReady, replace_same_volume

        calls = {"n": 0}
        real = replace_same_volume

        def flaky(src: Path, dest: Path) -> None:
            calls["n"] += 1
            if calls["n"] < 3:
                raise MoveNotReady("WinError 32: file in use")
            real(src, dest)

        with tempfile.TemporaryDirectory() as tmpname:
            tmp = Path(tmpname)
            deck = _sort_deck(tmp)
            src = tmp / "card.jpg"
            op = {"op": "move", "from": "card.jpg", "to": "keep/card.jpg"}
            os.environ["CHOICE_SYNC_WORK"] = "1"
            try:
                with patch("choice.file_moves.replace_same_volume", side_effect=flaky):
                    with patch("choice.work_queue._retry_delay_for_job", return_value=0.0):
                        from choice.work_queue import enqueue_file_op

                        enqueue_file_op(deck, "dec-2", op)
                        wait_idle(deck.state_dir, timeout=30.0)
                self.assertGreaterEqual(calls["n"], 3)
                self.assertFalse(src.is_file())
                self.assertTrue((tmp / "keep" / "card.jpg").is_file())
            finally:
                os.environ.pop("CHOICE_SYNC_WORK", None)

    def test_media_read_releases_before_rename(self):
        from choice.media import prepare_file

        with tempfile.TemporaryDirectory() as tmpname:
            tmp = Path(tmpname)
            src = tmp / "card.jpg"
            src.write_bytes(b"\xff\xd8\xff" + b"x" * 2000)
            cache = tmp / "cache"
            served = prepare_file(src, cache, full=True, etag_version="t")
            assert served.path is not None
            os.replace(src, tmp / "moved.jpg")
            self.assertFalse(src.is_file())
            self.assertTrue((tmp / "moved.jpg").is_file())

    def test_move_waits_for_inflight_media_read(self):
        import time

        from choice.file_moves import move_file
        from choice.source_reads import wait_source_idle

        def wait_until(predicate, timeout: float = 5.0) -> bool:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if predicate():
                    return True
                time.sleep(0.01)
            return False

        with tempfile.TemporaryDirectory() as tmpname:
            tmp = Path(tmpname)
            src = tmp / "card.jpg"
            src.write_bytes(b"data")
            dest = tmp / "keep" / "card.jpg"
            dest.parent.mkdir()
            release = threading.Event()
            holding = threading.Event()

            def reader():
                with hold_source_read(src):
                    holding.set()
                    release.wait(timeout=5.0)

            reader_thread = threading.Thread(target=reader)
            reader_thread.start()
            self.assertTrue(holding.wait(timeout=5.0))
            self.assertFalse(wait_source_idle(src, timeout=0.05))

            moved = threading.Event()

            def do_move():
                move_file(src, dest)
                moved.set()

            move_thread = threading.Thread(target=do_move)
            move_thread.start()
            self.assertTrue(
                wait_until(
                    lambda: move_thread.is_alive()
                    and not moved.is_set()
                    and src.is_file()
                    and not wait_source_idle(src, timeout=0.0),
                    timeout=5.0,
                )
            )
            release.set()
            reader_thread.join(timeout=5.0)
            self.assertTrue(moved.wait(timeout=10.0))
            move_thread.join(timeout=1.0)
            self.assertTrue(dest.is_file())


if __name__ == "__main__":
    unittest.main()
