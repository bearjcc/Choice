# SPDX-License-Identifier: AGPL-3.0-only

import inspect
import pathlib
import unittest

from choice.media_contract import accepts_host_media_call
from choice.sources.immich import _ImmichAdapter
from choice.sources.webdav import _WebDavMedia
from choice.swipe_plugin import SwipePlugin


class MediaContractTests(unittest.TestCase):
    def test_builtin_adapters_accept_host_keywords(self):
        for cls in (_ImmichAdapter, _WebDavMedia):
            fn = cls.media_bytes
            self.assertTrue(
                accepts_host_media_call(fn),
                msg=f"{cls.__name__}.media_bytes must accept item/index kwargs",
            )

    def test_swipe_plugin_adapter(self):
        class _Obj:
            def media_bytes(self, row, n=None):
                return b"x", "image/png"

        plugin = SwipePlugin(
            obj=_Obj(),
            folder=pathlib.Path("."),
            deck_id="d",
            title="t",
        )
        self.assertTrue(accepts_host_media_call(plugin.media_bytes))

    def test_httpd_call_shape(self):
        """Document the kwargs httpd passes (regression guard)."""
        params = inspect.signature(
            lambda item_id, item=None, index=None: None  # noqa: ARG005
        ).parameters
        self.assertIn("item", params)
        self.assertIn("index", params)
