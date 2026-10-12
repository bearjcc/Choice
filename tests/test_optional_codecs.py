# SPDX-License-Identifier: AGPL-3.0-only

import sys
import unittest
from unittest.mock import MagicMock, patch

from choice.optional_codecs import register_optional_codecs


class OptionalCodecTests(unittest.TestCase):
    def test_register_heif_and_jxl_openers(self):
        heif = MagicMock()
        heif.register_heif_opener = MagicMock()
        jxl = MagicMock()
        jxl.register_jxl_opener = MagicMock()
        with patch.dict(sys.modules, {"pillow_heif": heif, "pillow_jxl": jxl}):
            register_optional_codecs()
        heif.register_heif_opener.assert_called_once()
        jxl.register_jxl_opener.assert_called_once()

    def test_jxl_import_without_register_hook(self):
        heif = MagicMock()
        jxl = MagicMock(spec=[])
        with patch.dict(sys.modules, {"pillow_heif": heif, "pillow_jxl": jxl}):
            register_optional_codecs()
        heif.register_heif_opener.assert_called_once()

    def test_missing_packages_do_not_raise(self):
        import builtins

        real_import = builtins.__import__

        def _import(name, *args, **kwargs):
            if name in {"pillow_heif", "pillow_jxl"}:
                raise ImportError(name)
            return real_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", _import):
            register_optional_codecs()


if __name__ == "__main__":
    unittest.main()
