# SPDX-License-Identifier: AGPL-3.0-only

import json
import tempfile
import threading
import unittest
from pathlib import Path

from choice.atomic_io import write_json_atomic


class AtomicIoConcurrentTests(unittest.TestCase):
    def test_many_threads_same_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "folder_index.json"
            errors: list[BaseException] = []
            payloads = [{"n": i, "tag": f"v{i}"} for i in range(32)]
            barrier = threading.Barrier(len(payloads))

            def worker(payload: dict) -> None:
                try:
                    barrier.wait(timeout=5)
                    write_json_atomic(target, payload)
                except BaseException as exc:
                    errors.append(exc)

            threads = [
                threading.Thread(target=worker, args=(payload,)) for payload in payloads
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=30)
            self.assertEqual(errors, [])
            self.assertTrue(target.is_file())
            final = json.loads(target.read_text(encoding="utf-8"))
            self.assertIn(final["tag"], {p["tag"] for p in payloads})
            self.assertEqual(final, next(p for p in payloads if p["tag"] == final["tag"]))
            leftovers = list(Path(tmp).glob("*.tmp"))
            self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
