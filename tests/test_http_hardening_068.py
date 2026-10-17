# SPDX-License-Identifier: AGPL-3.0-only

import json
import os
import socket
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from choice import error_log
from choice.act import decide
from choice.httpd import ChoiceSite
from choice.open import open_config
from choice.server_settings import parse_server_settings
from choice.swipe_plugin import _accepts

FIX = Path(__file__).resolve().parent / "fixtures" / "plugin_host"


class RequestQueueSizeTests(unittest.TestCase):
    def test_config_and_env(self):
        cfg = parse_server_settings({"http": {"request_queue_size": 256}})
        self.assertEqual(cfg.http.request_queue_size, 256)
        os.environ["CHOICE_HTTP_REQUEST_QUEUE_SIZE"] = "512"
        try:
            from choice.env_config import _apply_server_env

            _apply_server_env(cfg)
            self.assertEqual(cfg.http.request_queue_size, 512)
        finally:
            os.environ.pop("CHOICE_HTTP_REQUEST_QUEUE_SIZE", None)

    def test_site_uses_configured_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg_path = root / "choice.toml"
            cfg_path.write_text(
                f"""
[state]
dir = "state"

[[sources]]
id = "s"
type = "swipe"
path = "{FIX.as_posix()}"

[[decks]]
id = "d"
title = "D"
source = "s"
mount = "filtered_list"

[http]
request_queue_size = 200
""".strip(),
                encoding="utf-8",
            )
            ChoiceSite.allow_reuse_address = True
            server = ChoiceSite(("127.0.0.1", 0), root, config_path=cfg_path)
            self.assertEqual(server.request_queue_size, 200)
            server.server_close()


class PortBindTests(unittest.TestCase):
    def test_second_bind_fails_without_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ChoiceSite.allow_reuse_address = False
            first = ChoiceSite(("127.0.0.1", 0), root)
            port = first.server_address[1]
            try:
                with self.assertRaises(OSError):
                    ChoiceSite(("127.0.0.1", port), root)
            finally:
                first.server_close()


class ErrorLogTests(unittest.TestCase):
    def tearDown(self):
        error_log.shutdown()

    def test_rotating_log_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            path = error_log.configure(state)
            error_log.log_exception("test", ValueError("boom"))
            error_log.shutdown()
            self.assertTrue(path.is_file())
            text = path.read_text(encoding="utf-8")
            self.assertIn("boom", text)
            error_log.configure(state)
            self.assertIn(str(path), error_log.user_detail_hint())


class AcceptsKwargsFilterTests(unittest.TestCase):
    def test_var_keyword_counts_as_filter(self):
        def wrapper(filter=None, **kwargs):
            return []

        self.assertTrue(_accepts(wrapper, "filter"))


class PluginErrorLogTests(unittest.TestCase):
    def tearDown(self):
        error_log.shutdown()

    def test_plugin_error_text_mentions_log(self):
        from choice.act import _plugin_error_text

        with tempfile.TemporaryDirectory() as tmp:
            error_log.configure(Path(tmp))
            msg = _plugin_error_text(RuntimeError("plugin blew up"))
            self.assertIn("choice-errors.log", msg)
            self.assertIn("plugin blew up", msg)
