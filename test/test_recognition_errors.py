# pyright: reportMissingImports=false

import unittest
from unittest import mock


class TestRecognitionErrors(unittest.TestCase):
    def test_mathcraft_failure_classifier_reports_missing_cache(self):
        from backend.mathcraft.model import classify_mathcraft_failure

        info = classify_mathcraft_failure(
            "MathCraft runtime is not ready: missing=['mathcraft-formula-rec'], unsupported=[]"
        )
        self.assertEqual(info["code"], "MODEL_CACHE_INCOMPLETE")

    def test_mathcraft_failure_classifier_reports_cuda_runtime(self):
        from backend.mathcraft.model import classify_mathcraft_failure

        info = classify_mathcraft_failure(
            "Failed to create CUDAExecutionProvider. Require cuDNN 9.* and CUDA 12.*. "
            "LoadLibrary failed with error 126 when trying to load "
            "onnxruntime_providers_cuda.dll"
        )
        self.assertEqual(info["code"], "CUDA_RUNTIME_BROKEN")

    def test_mathcraft_failure_classifier_reports_broken_onnxruntime(self):
        from backend.mathcraft.model import classify_mathcraft_failure

        info = classify_mathcraft_failure(
            "onnxruntime dependency is incomplete: missing get_available_providers "
            "(origin=<namespace package>)"
        )
        self.assertEqual(info["code"], "ONNXRUNTIME_BROKEN")

    def test_mathcraft_failure_classifier_reports_broken_onnxruntime_without_patterns_module(
        self,
    ):
        from backend.mathcraft.model import classify_mathcraft_failure

        real_import = __import__

        def _blocked_import(name, globals=None, locals=None, fromlist=(), level=0):
            if (
                name == "mathcraft_ocr.error_patterns"
                and "looks_like_onnxruntime_install_error" in fromlist
            ):
                raise ImportError("simulated missing new error pattern")
            return real_import(name, globals, locals, fromlist, level)

        with mock.patch("builtins.__import__", side_effect=_blocked_import):
            info = classify_mathcraft_failure(
                "onnxruntime dependency is incomplete: missing get_available_providers "
                "(origin=<namespace package>)"
            )

        self.assertEqual(info["code"], "ONNXRUNTIME_BROKEN")

    def test_mathcraft_failure_classifier_ignores_empty_missing_cache(self):
        from backend.mathcraft.model import classify_mathcraft_failure

        info = classify_mathcraft_failure(
            "MathCraft runtime is not ready: missing=[], unsupported=[]"
        )
        self.assertNotEqual(info["code"], "MODEL_CACHE_INCOMPLETE")

    def test_external_model_failure_message_is_not_mathcraft_classified(self):
        from recognition.error_messages import recognition_failure_user_message

        raw = "HTTPConnectionPool(host='127.0.0.1', port=11434): raw upstream failure"
        message = recognition_failure_user_message(raw, "external_model")
        self.assertIn("外部模型", message)
        self.assertNotIn("HTTPConnectionPool", message)

    def test_recognition_error_codes_have_chinese_user_messages(self):
        from recognition.error_messages import recognition_error_code_user_message

        for code in (
            "queue_full",
            "model_unavailable",
            "upstream_timeout",
            "internal_error",
            "unknown",
        ):
            message = recognition_error_code_user_message(code)
            self.assertRegex(message, r"[\u4e00-\u9fff]")

    def test_mathcraft_failure_message_still_uses_mathcraft_classifier(self):
        from recognition.error_messages import recognition_failure_user_message

        message = recognition_failure_user_message(
            "CUDAExecutionProvider failed", "mathcraft"
        )
        self.assertIn("CUDA", message)

    def test_empty_recognition_failure_message_is_preserved(self):
        from recognition.error_messages import recognition_failure_user_message

        self.assertEqual(
            recognition_failure_user_message("未识别到公式内容", "mathcraft"),
            "未识别到公式内容",
        )

    def test_mathcraft_failure_classifier_reports_gpu_provider_failure(self):
        from backend.mathcraft.model import classify_mathcraft_failure

        info = classify_mathcraft_failure(
            "GPU provider was requested but none is available: ('CPUExecutionProvider',)"
        )

        self.assertEqual(info["code"], "GPU_PROVIDER_UNAVAILABLE")
