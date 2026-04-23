# pyright: reportMissingImports=false
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _deps_bootstrap():
    import deps_bootstrap

    return deps_bootstrap


def _model_symbols():
    from backend.model import ModelWrapper, classify_pix2text_failure

    return ModelWrapper, classify_pix2text_failure


class CoreVerifyAndOcrCacheTests(unittest.TestCase):
    def test_core_default_verify_is_lightweight(self):
        deps_bootstrap = _deps_bootstrap()
        self.assertIs(
            deps_bootstrap.LAYER_VERIFY_CODE["CORE"],
            deps_bootstrap._CORE_LIGHT_VERIFY_CODE,
        )
        self.assertIs(
            deps_bootstrap.LAYER_VERIFY_CODE_STRICT["CORE"],
            deps_bootstrap._CORE_PIX2TEXT_VERIFY_CODE,
        )

    def test_core_light_verify_does_not_bootstrap_pix2text(self):
        deps_bootstrap = _deps_bootstrap()
        code = deps_bootstrap._CORE_LIGHT_VERIFY_CODE
        self.assertNotIn("Pix2Text.from_config", code)
        self.assertIn("from pix2text import Pix2Text", code)

    def test_ocr_cache_error_is_classified(self):
        _, classify_pix2text_failure = _model_symbols()
        detail = (
            r"FileNotFoundError: C:\Users\foo\AppData\Roaming\cnstd\1.2\ppocr"
            r"\ch_PP-OCRv5_det\ch_PP-OCRv5_det_infer.onnx does not exists."
        )
        info = classify_pix2text_failure(detail)
        self.assertEqual(info["code"], "BROKEN_OCR_MODEL_CACHE")

    def test_ocr_cache_retry_gate_matches_classifier(self):
        ModelWrapper, _ = _model_symbols()
        dummy = ModelWrapper.__new__(ModelWrapper)
        detail = (
            r"rapidocr failed: C:\Users\foo\AppData\Roaming\cnocr\2.3"
            r"\densenet_lite_136-gru\model.onnx does not exists."
        )
        self.assertTrue(ModelWrapper._is_incomplete_ocr_model_cache_error(dummy, detail))

    def test_table_cache_error_is_classified(self):
        _, classify_pix2text_failure = _model_symbols()
        detail = (
            r"OSError: E:\cache\pix2text\1.1\table-rec does not appear to have "
            r"a file named config.json. Checkout 'https://huggingface.co/E:\cache\pix2text\1.1\table-rec/tree/None' "
            r"for available files."
        )
        info = classify_pix2text_failure(detail)
        self.assertEqual(info["code"], "BROKEN_TABLE_MODEL_CACHE")

    def test_force_cpu_ort_flag_is_injected_only_when_enabled(self):
        ModelWrapper, _ = _model_symbols()
        dummy = ModelWrapper.__new__(ModelWrapper)
        dummy._force_ort_cpu_only = False
        env = ModelWrapper._build_subprocess_env(dummy)
        self.assertNotIn("LATEXSNIPPER_FORCE_ORT_CPU", env)

        dummy._force_ort_cpu_only = True
        env = ModelWrapper._build_subprocess_env(dummy)
        self.assertEqual(env.get("LATEXSNIPPER_FORCE_ORT_CPU"), "1")


if __name__ == "__main__":
    unittest.main()
