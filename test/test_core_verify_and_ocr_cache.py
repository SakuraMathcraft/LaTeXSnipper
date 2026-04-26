# pyright: reportMissingImports=false

import inspect
import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
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

    def test_mathcraft_failure_classifier_reports_cuda_runtime(self):
        from backend.model import classify_mathcraft_failure

        info = classify_mathcraft_failure(
            "Failed to create CUDAExecutionProvider. Require cuDNN 9.* and CUDA 12.*. "
            "LoadLibrary failed with error 126 when trying to load "
            "onnxruntime_providers_cuda.dll"
        )
        self.assertEqual(info["code"], "CUDA_RUNTIME_BROKEN")

    def test_mathcraft_failure_classifier_reports_broken_onnxruntime(self):
        from backend.model import classify_mathcraft_failure

        info = classify_mathcraft_failure(
            "onnxruntime dependency is incomplete: missing get_available_providers "
            "(origin=<namespace package>)"
        )
        self.assertEqual(info["code"], "ONNXRUNTIME_BROKEN")

    def test_mathcraft_failure_classifier_reports_broken_onnxruntime_without_patterns_module(self):
        from backend.model import classify_mathcraft_failure

        real_import = __import__

        def _blocked_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "mathcraft_ocr.error_patterns" and "looks_like_onnxruntime_install_error" in fromlist:
                raise ImportError("simulated missing new error pattern")
            return real_import(name, globals, locals, fromlist, level)

        with mock.patch("builtins.__import__", side_effect=_blocked_import):
            info = classify_mathcraft_failure(
                "onnxruntime dependency is incomplete: missing get_available_providers "
                "(origin=<namespace package>)"
            )

        self.assertEqual(info["code"], "ONNXRUNTIME_BROKEN")

    def test_mathcraft_failure_classifier_ignores_empty_missing_cache(self):
        from backend.model import classify_mathcraft_failure

        info = classify_mathcraft_failure(
            "MathCraft runtime is not ready: missing=[], unsupported=[]"
        )
        self.assertNotEqual(info["code"], "MODEL_CACHE_INCOMPLETE")

    def test_external_model_failure_message_is_not_mathcraft_classified(self):
        from backend.recognition_errors import recognition_failure_user_message

        raw = "无法连接到 127.0.0.1:11434，请确认服务已启动。"
        self.assertEqual(
            recognition_failure_user_message(raw, "external_model"),
            raw,
        )

    def test_mathcraft_failure_message_still_uses_mathcraft_classifier(self):
        from backend.recognition_errors import recognition_failure_user_message

        message = recognition_failure_user_message("CUDAExecutionProvider failed", "mathcraft")
        self.assertIn("CUDA", message)

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

    def test_cleanup_removes_orphan_onnxruntime_namespace(self):
        import deps_bootstrap

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pyexe = root / "python311" / "python.exe"
            site_packages = root / "python311" / "Lib" / "site-packages"
            orphan = site_packages / "onnxruntime"
            orphan.mkdir(parents=True)
            pyexe.parent.mkdir(parents=True, exist_ok=True)
            pyexe.write_text("", encoding="utf-8")

            with mock.patch("deps_bootstrap._current_installed", return_value={}):
                removed = deps_bootstrap._cleanup_orphan_onnxruntime_namespace(pyexe)

            self.assertEqual(removed, 1)
            self.assertFalse(orphan.exists())

    def test_subprocess_env_points_worker_at_repo_root(self):
        from backend.model import ModelWrapper

        wrapper = ModelWrapper(auto_warmup=False)
        env = wrapper._build_subprocess_env()

        pythonpath_roots = {Path(item) for item in env["PYTHONPATH"].split(os.pathsep) if item}
        self.assertIn(ROOT, pythonpath_roots)
        self.assertEqual(env["PYTHONNOUSERSITE"], "1")

    def test_unknown_modes_fall_back_to_formula(self):
        from backend.model import ModelWrapper

        wrapper = ModelWrapper(auto_warmup=False)
        self.assertEqual(wrapper._mode_for_model("unknown_mode"), "formula")

    def test_mathcraft_provider_prefers_installed_gpu_layer(self):
        from backend.model import _infer_provider_preference_from_deps_state
        from mathcraft_ocr.providers import GPU_PROVIDER_NAMES

        self.assertEqual(GPU_PROVIDER_NAMES[0], "CUDAExecutionProvider")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pyexe = root / "python311" / "python.exe"
            pyexe.parent.mkdir()
            pyexe.write_text("", encoding="utf-8")
            (root / ".deps_state.json").write_text(
                json.dumps({"installed_layers": ["BASIC", "CORE", "MATHCRAFT_GPU"]}),
                encoding="utf-8",
            )
            self.assertEqual(_infer_provider_preference_from_deps_state(str(pyexe)), "gpu")

    def test_explicit_mathcraft_provider_env_wins(self):
        from backend.model import resolve_mathcraft_provider_preference

        old = os.environ.get("MATHCRAFT_PROVIDER")
        os.environ["MATHCRAFT_PROVIDER"] = "cpu"
        try:
            self.assertEqual(resolve_mathcraft_provider_preference(), "cpu")
        finally:
            if old is None:
                os.environ.pop("MATHCRAFT_PROVIDER", None)
            else:
                os.environ["MATHCRAFT_PROVIDER"] = old

    def test_settings_probe_covers_packaged_internal_root(self):
        source = (SRC / "settings_window.py").read_text(encoding="utf-8")

        self.assertIn("def _mathcraft_code_roots", source)
        self.assertIn('parent / "_internal"', source)
        self.assertIn("sys._MEIPASS", source)


class DependencyBootstrapMathCraftTests(unittest.TestCase):
    def test_mathcraft_package_version_matches_public_init(self):
        import mathcraft_ocr

        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        match = re.search(r'^version = "([^"]+)"', pyproject, re.MULTILINE)

        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.group(1), mathcraft_ocr.__version__)

    def test_mathcraft_package_metadata_covers_runtime_support_deps(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()

        for dep in (
            "coloredlogs",
            "flatbuffers",
            "protobuf",
            "sentencepiece",
        ):
            self.assertIn(dep, pyproject)

    def test_dependency_layers_are_mathcraft_onnx_only(self):
        import deps_bootstrap

        self.assertIn("MATHCRAFT_CPU", deps_bootstrap.LAYER_MAP)
        self.assertIn("MATHCRAFT_GPU", deps_bootstrap.LAYER_MAP)

        all_specs = "\n".join(
            spec for specs in deps_bootstrap.LAYER_MAP.values() for spec in specs
        ).lower()
        self.assertIn("onnxruntime", all_specs)
        self.assertIn("numpy", all_specs)
        self.assertIn("protobuf", all_specs)
        self.assertNotIn("argostranslate", all_specs)

    def test_layer_verify_code_uses_single_core_path(self):
        import deps_bootstrap

        verify_code = "\n".join(str(v) for v in deps_bootstrap.LAYER_VERIFY_CODE.values()).lower()
        self.assertIn("cudaexecutionprovider", verify_code)

    def test_mathcraft_backend_selection_is_mutually_exclusive(self):
        import deps_bootstrap

        chosen = deps_bootstrap._normalize_chosen_layers(
            ["BASIC", "MATHCRAFT_CPU", "MATHCRAFT_GPU"]
        )
        self.assertEqual(chosen, ["BASIC", "MATHCRAFT_GPU"])

    def test_onnxruntime_install_path_does_not_force_dependency_reinstall(self):
        source = (SRC / "deps_bootstrap.py").read_text(encoding="utf-8").lower()
        force_block = source.split("force_reinstall_pkgs = {", 1)[1].split("}", 1)[0]

        self.assertNotIn("onnxruntime", force_block)
        self.assertIn('if name in {"onnxruntime", "onnxruntime-gpu"}:', source)
        self.assertIn('args.append("--no-deps")', source)

    def test_critical_repair_covers_onnxruntime_dependency_chain(self):
        import deps_bootstrap

        for pkg in ("numpy", "sympy", "flatbuffers", "packaging", "coloredlogs", "protobuf"):
            self.assertIn(pkg, deps_bootstrap.CRITICAL_VERSIONS)

        source = inspect.getsource(deps_bootstrap._repair_gpu_onnxruntime_runtime)
        self.assertIn("_fix_critical_versions", source)
        self.assertIn("force_reinstall=False", source)
        self.assertNotIn("force_reinstall=True", source)

    def test_pip_interrupted_leftovers_are_cleaned_from_target_site(self):
        import deps_bootstrap

        with tempfile.TemporaryDirectory() as d:
            site = Path(d) / "site-packages"
            site.mkdir()
            leftover_dir = site / "~umpy"
            leftover_dist = site / "~ympy-1.14.0.dist-info"
            normal_dir = site / "numpy"
            leftover_dir.mkdir()
            leftover_dist.mkdir()
            normal_dir.mkdir()

            original = deps_bootstrap._site_packages_root
            deps_bootstrap._site_packages_root = lambda _pyexe: site
            try:
                removed = deps_bootstrap._cleanup_pip_interrupted_leftovers(
                    Path(d) / "python.exe"
                )
            finally:
                deps_bootstrap._site_packages_root = original

            self.assertEqual(removed, 2)
            self.assertFalse(leftover_dir.exists())
            self.assertFalse(leftover_dist.exists())
            self.assertTrue(normal_dir.exists())

    def test_pyinstaller_spec_keeps_psutil_for_packaged_speed_meter(self):
        spec = (ROOT / "LaTeXSnipper.spec").read_text(encoding="utf-8")
        hiddenimports = re.search(r"hiddenimports=\[(.*?)\],", spec, re.S)
        excludes = re.search(r"excludes=\[(.*?)\],", spec, re.S)
        prune_prefixes = re.search(r"remove_prefixes = \((.*?)\)", spec, re.S)

        self.assertIsNotNone(hiddenimports)
        self.assertIsNotNone(excludes)
        self.assertIsNotNone(prune_prefixes)
        self.assertIn('"psutil"', hiddenimports.group(1))
        self.assertNotIn('"psutil"', excludes.group(1))
        self.assertNotIn('"psutil"', prune_prefixes.group(1))

    def test_dependency_logs_distinguish_support_imports_from_final_layer_verify(self):
        source = (SRC / "deps_bootstrap.py").read_text(encoding="utf-8")

        self.assertIn("ONNX Runtime 支撑依赖导入检查通过", source)
        self.assertNotIn("onnxruntime-gpu runtime check passed", source)
        self.assertNotIn("onnxruntime CPU runtime check passed", source)
        self.assertNotIn("Dependencies installed ✅", source)


if __name__ == "__main__":
    unittest.main()
