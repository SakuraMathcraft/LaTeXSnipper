import os
import unittest
from pathlib import Path
from unittest import mock

import sys

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import backend.model_factory as mf


class Phase1ModelFactoryTests(unittest.TestCase):
    def test_daemon_mode_defaults_to_enabled(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertTrue(mf._use_daemon_mode())

    def test_daemon_mode_can_be_explicitly_disabled(self):
        with mock.patch.dict(os.environ, {"LATEXSNIPPER_USE_DAEMON": "0"}, clear=True):
            self.assertFalse(mf._use_daemon_mode())

    def test_create_model_wrapper_uses_daemon_when_enabled(self):
        with mock.patch.object(mf, "_use_daemon_mode", return_value=True):
            with mock.patch("backend.model_daemon_adapter.DaemonModelWrapper", return_value="daemon-wrapper"):
                out = mf.create_model_wrapper("pix2text")
        self.assertEqual(out, "daemon-wrapper")

    def test_create_model_wrapper_fallbacks_to_local(self):
        with mock.patch.object(mf, "_use_daemon_mode", return_value=True):
            with mock.patch("backend.model_daemon_adapter.DaemonModelWrapper", side_effect=RuntimeError("boom")):
                with mock.patch.object(mf, "ModelWrapper", return_value="local-wrapper"):
                    out = mf.create_model_wrapper("pix2text")
        self.assertEqual(out, "local-wrapper")


if __name__ == "__main__":
    unittest.main()
