import unittest
from unittest import mock
from pathlib import Path
import sys

from PIL import Image

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from backend.model import ModelWrapper


class Phase0ModelRoutingTests(unittest.TestCase):
    def _new_wrapper(self, ready: bool = True):
        w = ModelWrapper.__new__(ModelWrapper)
        w._pix2text_subprocess_ready = ready
        w._pix2text_import_failed = False
        w.last_used_model = None
        w._lazy_load_pix2text = mock.Mock(return_value=ready)
        w._run_pix2text_subprocess = mock.Mock(return_value="ok")
        return w

    def test_predict_routes_mode_by_model_name(self):
        img = Image.new("RGB", (2, 2), "white")
        cases = {
            "pix2text": "formula",
            "pix2text_text": "text",
            "pix2text_mixed": "mixed",
            "pix2text_page": "page",
            "pix2text_table": "table",
        }
        for model_name, mode in cases.items():
            with self.subTest(model_name=model_name):
                w = self._new_wrapper(ready=True)
                out = ModelWrapper.predict(w, img, model_name=model_name)
                self.assertEqual(out, "ok")
                w._run_pix2text_subprocess.assert_called_once()
                self.assertEqual(w._run_pix2text_subprocess.call_args.kwargs["mode"], mode)
                self.assertEqual(w.last_used_model, model_name)

    def test_predict_fallbacks_to_formula_for_unknown_model(self):
        img = Image.new("RGB", (2, 2), "white")
        w = self._new_wrapper(ready=True)
        out = ModelWrapper.predict(w, img, model_name="unknown_model")
        self.assertEqual(out, "ok")
        self.assertEqual(w._run_pix2text_subprocess.call_args.kwargs["mode"], "formula")
        self.assertEqual(w.last_used_model, "pix2text")

    def test_predict_raises_when_model_not_ready(self):
        img = Image.new("RGB", (2, 2), "white")
        w = self._new_wrapper(ready=False)
        w._lazy_load_pix2text.return_value = False
        with self.assertRaisesRegex(RuntimeError, "pix2text not ready"):
            ModelWrapper.predict(w, img, model_name="pix2text")
        w._lazy_load_pix2text.assert_called_once()


if __name__ == "__main__":
    unittest.main()
