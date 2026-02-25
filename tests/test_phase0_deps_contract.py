import unittest
from pathlib import Path
import sys
from unittest import mock

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import deps_bootstrap as db


class Phase0DepsContractTests(unittest.TestCase):
    def test_sanitize_state_heavy_conflict_default_prefers_gpu(self):
        state = {
            "installed_layers": ["BASIC", "CORE", "HEAVY_CPU", "HEAVY_GPU"],
            "failed_layers": [],
        }
        with mock.patch.object(db, "_save_json", return_value=None):
            out = db._sanitize_state_layers(Path("dummy_state.json"), state=state)
        self.assertIn("HEAVY_GPU", out["installed_layers"])
        self.assertNotIn("HEAVY_CPU", out["installed_layers"])

    def test_sanitize_state_heavy_conflict_prefers_cpu_when_gpu_failed(self):
        state = {
            "installed_layers": ["BASIC", "CORE", "HEAVY_CPU", "HEAVY_GPU"],
            "failed_layers": ["HEAVY_GPU"],
        }
        with mock.patch.object(db, "_save_json", return_value=None):
            out = db._sanitize_state_layers(Path("dummy_state.json"), state=state)
        self.assertIn("HEAVY_CPU", out["installed_layers"])
        self.assertNotIn("HEAVY_GPU", out["installed_layers"])

    def test_gpu_reinstall_decision_for_torch_variants(self):
        self.assertTrue(db._needs_torch_reinstall_for_gpu("2.7.1+cpu", "cu118"))
        self.assertTrue(db._needs_torch_reinstall_for_gpu("2.7.1", "cu118"))
        self.assertTrue(db._needs_torch_reinstall_for_gpu("2.7.1+cu118", "cu126"))
        self.assertFalse(db._needs_torch_reinstall_for_gpu("2.7.1+cu126", "cu126"))

    def test_matrix_for_cu118(self):
        specs = db._torch_specs_for_index_url("https://download.pytorch.org/whl/cu118", prefer_gpu=True)
        self.assertEqual(specs["torch"], "torch==2.7.1")
        self.assertEqual(specs["torchvision"], "torchvision==0.22.1")
        self.assertEqual(specs["torchaudio"], "torchaudio==2.7.1")
        ort = db._onnxruntime_gpu_spec_for_torch_url("https://download.pytorch.org/whl/cu118", prefer_gpu=True)
        self.assertEqual(ort, "onnxruntime-gpu~=1.18.1")


if __name__ == "__main__":
    unittest.main()
