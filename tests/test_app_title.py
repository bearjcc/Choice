# SPDX-License-Identifier: AGPL-3.0-only

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from choice.config import DEFAULT_APP_TITLE, load_config, resolve_app_title
from choice.httpd import ChoiceSite


class AppTitleConfigTests(unittest.TestCase):
    def test_default_title(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = root / "choice.toml"
            cfg.write_text(
                """
[state]
dir = "state"

[[sources]]
id = "s"
type = "folder"
path = "."

[[decks]]
id = "d"
title = "Deck"
source = "s"
mount = "."
""".strip(),
                encoding="utf-8",
            )
            loaded = load_config(cfg)
            self.assertEqual(loaded.app_title, DEFAULT_APP_TITLE)

    def test_toml_title(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = root / "choice.toml"
            cfg.write_text(
                """
title = "Spicy"

[state]
dir = "state"

[[sources]]
id = "s"
type = "folder"
path = "."

[[decks]]
id = "d"
title = "Deck"
source = "s"
mount = "."
""".strip(),
                encoding="utf-8",
            )
            self.assertEqual(load_config(cfg).app_title, "Spicy")

    def test_cli_overrides_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "choice.toml"
            cfg.write_text(
                """
title = "Sky"

[state]
dir = "state"

[[sources]]
id = "s"
type = "folder"
path = "."

[[decks]]
id = "d"
title = "Deck"
source = "s"
mount = "."
""".strip(),
                encoding="utf-8",
            )
            self.assertEqual(resolve_app_title(cfg, "Spicy"), "Spicy")
            self.assertEqual(resolve_app_title(cfg, None), "Sky")


class AppTitleHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp)

    def _fetch(self, port: int, path: str) -> tuple[int, bytes, str]:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as resp:
            return resp.status, resp.read(), resp.headers.get_content_type()

    def test_manifest_and_sw_under_base_path(self):
        ChoiceSite.allow_reuse_address = True
        server = ChoiceSite(
            ("127.0.0.1", 0),
            self.root,
            base_path="/spicy",
            app_title="Spicy",
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        try:
            code, body, ctype = self._fetch(port, "/spicy/manifest.webmanifest")
            self.assertEqual(code, 200)
            self.assertIn("manifest", ctype)
            manifest = json.loads(body.decode("utf-8"))
            self.assertEqual(manifest["name"], "Spicy")
            self.assertEqual(manifest["start_url"], "./")
            self.assertEqual(manifest["scope"], "./")

            code, sw_body, sw_type = self._fetch(port, "/spicy/sw.js")
            self.assertEqual(code, 200)
            self.assertIn("javascript", sw_type)
            self.assertIn(b"service worker", sw_body.lower())

            html = self._fetch(port, "/spicy/")[1].decode("utf-8")
            self.assertIn("<title>Spicy</title>", html)
            self.assertIn('name="choice-app-title" content="Spicy"', html)
            self.assertIn('href="manifest.webmanifest"', html)
            self.assertIn('<base href="/spicy/">', html)

            with self.assertRaises(urllib.error.HTTPError) as err:
                self._fetch(port, "/manifest.webmanifest")
            self.assertEqual(err.exception.code, 404)

            _, health_raw, _ = self._fetch(port, "/spicy/api/health")
            health = json.loads(health_raw.decode("utf-8"))
            self.assertEqual(health["app_title"], "Spicy")
            self.assertEqual(health["base_path"], "/spicy")
        finally:
            server.shutdown()
            server.server_close()

    def test_two_prefixes_do_not_share_manifest(self):
        ChoiceSite.allow_reuse_address = True
        sky = ChoiceSite(("127.0.0.1", 0), self.root, base_path="/sky", app_title="Sky")
        spicy = ChoiceSite(("127.0.0.1", 0), self.root, base_path="/spicy", app_title="Spicy")
        t1 = threading.Thread(target=sky.serve_forever, daemon=True)
        t2 = threading.Thread(target=spicy.serve_forever, daemon=True)
        t1.start()
        t2.start()
        sky_port = sky.server_address[1]
        spicy_port = spicy.server_address[1]
        try:
            _, sky_body, _ = self._fetch(sky_port, "/sky/manifest.webmanifest")
            _, spicy_body, _ = self._fetch(spicy_port, "/spicy/manifest.webmanifest")
            self.assertEqual(json.loads(sky_body.decode())["name"], "Sky")
            self.assertEqual(json.loads(spicy_body.decode())["name"], "Spicy")
        finally:
            sky.shutdown()
            spicy.shutdown()
            sky.server_close()
            spicy.server_close()


if __name__ == "__main__":
    unittest.main()
