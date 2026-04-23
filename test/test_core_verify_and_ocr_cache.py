# pyright: reportMissingImports=false

import inspect
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class InternalModelMathCraftTests(unittest.TestCase):
    def test_internal_model_wrapper_has_no_external_runtime_import(self):
        import backend.model as model_mod

        source = inspect.getsource(model_mod)
        self.assertIn("from mathcraft_ocr.cli import main", source)
        self.assertIn("MathCraft-only internal OCR wrapper", source)

    def test_mathcraft_failure_classifier_reports_missing_cache(self):
        from backend.model import classify_mathcraft_failure

        info = classify_mathcraft_failure(
            "MathCraft runtime is not ready: missing=['mathcraft-formula-rec'], unsupported=[]"
        )
        self.assertEqual(info["code"], "MODEL_CACHE_INCOMPLETE")

    def test_subprocess_env_points_worker_at_repo_root(self):
        from backend.model import ModelWrapper

        wrapper = ModelWrapper(auto_warmup=False)
        env = wrapper._build_subprocess_env()
        self.assertEqual(Path(env["PYTHONPATH"]), ROOT)
        self.assertEqual(env["PYTHONNOUSERSITE"], "1")

    def test_unknown_modes_fall_back_to_formula(self):
        from backend.model import ModelWrapper

        wrapper = ModelWrapper(auto_warmup=False)
        self.assertEqual(wrapper._mode_for_model("unknown_mode"), "formula")


if __name__ == "__main__":
    unittest.main()
