# SPDX-License-Identifier: AGPL-3.0-only

import json
import threading
import unittest
import urllib.request

from choice.httpd import ChoiceSite, normalize_base_path


class NormalizeBasePathTests(unittest.TestCase):
    def test_root(self):
        self.assertEqual(normalize_base_path(""), "")
        self.assertEqual(normalize_base_path("/"), "")
        self.assertEqual(normalize_base_path(None), "")

    def test_prefix(self):
        self.assertEqual(normalize_base_path("/choice"), "/choice")
        self.assertEqual(normalize_base_path("choice"), "/choice")
        self.assertEqual(normalize_base_path("/choice/"), "/choice")


class PrefixedHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = __import__("tempfile").mkdtemp()
        self.root = __import__("pathlib").Path(self.tmp)

    def _get(self, port: int, path: str) -> tuple[int, dict]:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def test_api_under_prefix(self):
        ChoiceSite.allow_reuse_address = True
        server = ChoiceSite(("127.0.0.1", 0), self.root, base_path="/choice")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        try:
            code, health = self._get(port, "/choice/api/health")
            self.assertEqual(code, 200)
            self.assertEqual(health.get("base_path"), "/choice")
            with self.assertRaises(urllib.error.HTTPError) as err:
                self._get(port, "/api/health")
            self.assertEqual(err.exception.code, 404)
        finally:
            server.shutdown()
            server.server_close()
