# pyright: reportMissingImports=false

import unittest
from unittest import mock


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
