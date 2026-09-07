# pyright: reportMissingImports=false

import json
import os
import tempfile
import unittest
from unittest import mock
from pathlib import Path


class TestMathcraftProviderPolicy(unittest.TestCase):
    def test_provider_reports_incomplete_onnxruntime_namespace(self):
        from mathcraft_ocr.errors import ProviderError
        from mathcraft_ocr.providers import detect_providers

        with mock.patch(
            "mathcraft_ocr.providers.importlib.import_module",
            return_value=object(),
        ):
            with self.assertRaises(ProviderError) as ctx:
                detect_providers()

        self.assertIn("missing get_available_providers", str(ctx.exception))

    def test_explicit_gpu_provider_does_not_fall_back_to_cpu(self):
        from mathcraft_ocr.errors import ProviderError
        from mathcraft_ocr.providers import detect_providers

        ort = mock.Mock()
        ort.get_available_providers.return_value = ["CPUExecutionProvider"]
        with (
            mock.patch(
                "mathcraft_ocr.providers.importlib.import_module",
                return_value=ort,
            ),
            self.assertRaises(ProviderError) as ctx,
        ):
            detect_providers("gpu")

        self.assertIn("GPU provider was requested", str(ctx.exception))

    def test_auto_provider_can_select_cpu_when_no_gpu_is_requested(self):
        from mathcraft_ocr.providers import detect_providers

        ort = mock.Mock()
        ort.get_available_providers.return_value = ["CPUExecutionProvider"]
        with mock.patch(
            "mathcraft_ocr.providers.importlib.import_module",
            return_value=ort,
        ):
            info = detect_providers("auto")

        self.assertEqual(info.active_provider, "CPUExecutionProvider")
        self.assertEqual(info.device, "cpu")

    def test_explicit_cpu_provider_ignores_available_gpu(self):
        from mathcraft_ocr.providers import detect_providers

        ort = mock.Mock()
        ort.get_available_providers.return_value = [
            "CUDAExecutionProvider",
            "CPUExecutionProvider",
        ]
        with mock.patch(
            "mathcraft_ocr.providers.importlib.import_module",
            return_value=ort,
        ):
            info = detect_providers("cpu")

        self.assertEqual(info.active_provider, "CPUExecutionProvider")
        self.assertEqual(info.device, "cpu")
        self.assertFalse(info.gpu_requested)

    def test_mathcraft_provider_prefers_installed_gpu_layer(self):
        from backend.mathcraft.model import _infer_provider_preference_from_deps_state
        from mathcraft_ocr.providers import GPU_PROVIDER_NAMES

        self.assertEqual(GPU_PROVIDER_NAMES[0], "CUDAExecutionProvider")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pyexe = root / "python" / "python.exe"
            pyexe.parent.mkdir()
            pyexe.write_text("", encoding="utf-8")
            (root / ".deps_state.json").write_text(
                json.dumps({"installed_layers": ["BASIC", "CORE", "MATHCRAFT_GPU"]}),
                encoding="utf-8",
            )
            self.assertEqual(
                _infer_provider_preference_from_deps_state(str(pyexe)), "gpu"
            )

    def test_explicit_mathcraft_provider_env_wins(self):
        from backend.mathcraft.model import resolve_mathcraft_provider_preference

        old = os.environ.get("MATHCRAFT_PROVIDER")
        os.environ["MATHCRAFT_PROVIDER"] = "cpu"
        try:
            self.assertEqual(resolve_mathcraft_provider_preference(), "cpu")
        finally:
            if old is None:
                os.environ.pop("MATHCRAFT_PROVIDER", None)
            else:
                os.environ["MATHCRAFT_PROVIDER"] = old
