# pyright: reportMissingImports=false

import tempfile
import unittest
from unittest import mock
from pathlib import Path


class TestUpdateInstallerCache(unittest.TestCase):
    def test_update_download_cache_uses_app_state_dir(self):
        import update.installer_cache as installer_cache

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with mock.patch.object(installer_cache, "app_state_dir", return_value=root):
                self.assertEqual(installer_cache._update_dir(), root / "updates")
                self.assertTrue((root / "updates").is_dir())
