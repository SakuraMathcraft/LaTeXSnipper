# pyright: reportMissingImports=false

import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TestDependencyInstallation(unittest.TestCase):
    def test_cleanup_removes_orphan_onnxruntime_namespace(self):
        from bootstrap import deps_runtime_verify

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pyexe = root / "python" / "python.exe"
            site_packages = root / "python" / "Lib" / "site-packages"
            orphan = site_packages / "onnxruntime"
            orphan.mkdir(parents=True)
            pyexe.parent.mkdir(parents=True, exist_ok=True)
            pyexe.write_text("", encoding="utf-8")

            with mock.patch(
                "bootstrap.deps_runtime_verify._current_installed", return_value={}
            ):
                removed = deps_runtime_verify._cleanup_orphan_onnxruntime_namespace(
                    pyexe
                )

            self.assertEqual(removed, 1)
            self.assertFalse(orphan.exists())

    def test_packaged_windows_initial_deps_dir_uses_bundled_deps(self):
        import application.python_runtime_resolver as resolver

        bundled = ROOT / "_internal" / "deps"
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch.object(resolver, "_is_packaged_mode", return_value=True):
                with mock.patch.object(resolver.os, "name", "nt"):
                    with mock.patch.object(
                        resolver,
                        "_get_bundled_deps_dir_for_packaged",
                        return_value=bundled,
                    ):
                        self.assertEqual(resolver._initial_deps_dir(), bundled)

    def test_mathcraft_backend_selection_is_mutually_exclusive(self):
        from bootstrap.deps_layer_specs import _normalize_chosen_layers

        chosen = _normalize_chosen_layers(["BASIC", "MATHCRAFT_CPU", "MATHCRAFT_GPU"])
        self.assertEqual(chosen, ["BASIC", "MATHCRAFT_GPU"])

    def test_onnxruntime_install_path_does_not_force_dependency_reinstall(self):
        from bootstrap.deps_pip_runner import PipInstallRunner

        log_q = mock.Mock()
        runner = PipInstallRunner(
            pyexe=sys.executable,
            pkg="onnxruntime",
            stop_event=mock.Mock(),
            log_q=log_q,
            suppress_args=[],
        )

        onnx_args = runner._build_install_args(
            sys.executable, "onnxruntime", "onnxruntime", 0, None
        )
        self.assertIn("--no-deps", onnx_args)
        self.assertNotIn("--force-reinstall", onnx_args)

        protobuf_args = runner._build_install_args(
            sys.executable, "protobuf", "protobuf", 0, None
        )
        self.assertIn("--force-reinstall", protobuf_args)

    def test_unsupported_onnxruntime_gpu_policy_stops_before_pip(self):
        from bootstrap.deps_pip_runner import PipInstallRunner

        log_q = mock.Mock()
        runner = PipInstallRunner(
            pyexe=sys.executable,
            pkg="onnxruntime-gpu",
            stop_event=mock.Mock(),
            log_q=log_q,
            onnxruntime_gpu_policy=lambda _pyexe: type(
                "Policy",
                (),
                {"error": "unsupported CUDA/Python combination"},
            )(),
        )

        self.assertFalse(runner.install())
        log_q.put.assert_called_once_with("[ERR] unsupported CUDA/Python combination")

    def test_runtime_support_repair_specs_match_dependency_layer(self):
        from bootstrap.deps_layer_specs import LAYER_MAP
        from bootstrap.deps_runtime_verify import RUNTIME_SUPPORT_SPECS

        core_specs = set(LAYER_MAP["CORE"])
        for spec in RUNTIME_SUPPORT_SPECS.values():
            self.assertIn(spec, core_specs)

    def test_onnxruntime_support_repair_preserves_requested_backend(self):
        from bootstrap import deps_runtime_verify

        verify = mock.Mock(side_effect=[(False, "broken"), (True, "")])
        repair = mock.Mock(return_value=(True, ""))
        with mock.patch.object(
            deps_runtime_verify, "_verify_onnxruntime_runtime", verify
        ):
            with mock.patch.object(
                deps_runtime_verify, "_force_repair_broken_runtime_imports", repair
            ):
                ok, error = deps_runtime_verify._verify_onnxruntime_with_support_repair(
                    sys.executable,
                    expect_gpu=False,
                    log_fn=mock.Mock(),
                )

        self.assertTrue(ok)
        self.assertEqual(error, "")
        self.assertEqual(verify.call_count, 2)
        for call in verify.call_args_list:
            self.assertFalse(call.kwargs["expect_gpu"])

    def test_onnxruntime_gpu_policy_tracks_cuda_major(self):
        from backend.mathcraft.runtime_policy import (
            CUDA11_ORT_INDEX_URL,
            CudaRuntimeInfo,
            onnxruntime_cpu_spec,
            onnxruntime_gpu_policy,
        )

        self.assertEqual(
            onnxruntime_cpu_spec(python_version=(3, 10)),
            "onnxruntime>=1.20,<1.30",
        )

        cuda11 = onnxruntime_gpu_policy(
            cuda_info=CudaRuntimeInfo(major=11, minor=8, source="test"),
            python_version=(3, 11),
        )
        self.assertEqual(cuda11.requirement, "onnxruntime-gpu>=1.20,<1.21")
        self.assertEqual(cuda11.index_url, CUDA11_ORT_INDEX_URL)
        self.assertEqual(cuda11.expected_cudnn_major, 8)

        cuda12 = onnxruntime_gpu_policy(
            cuda_info=CudaRuntimeInfo(major=12, minor=4, source="test"),
            python_version=(3, 11),
        )
        self.assertEqual(cuda12.requirement, "onnxruntime-gpu>=1.21,<1.27")
        self.assertEqual(cuda12.index_url, "")
        self.assertEqual(cuda12.expected_cudnn_major, 9)

        cuda13 = onnxruntime_gpu_policy(
            cuda_info=CudaRuntimeInfo(major=13, minor=0, source="test"),
            python_version=(3, 11),
        )
        self.assertEqual(cuda13.requirement, "onnxruntime-gpu>=1.27,<1.30")
        self.assertEqual(cuda13.index_url, "")
        self.assertEqual(cuda13.source_label, "PyPI CUDA 13 wheels")

        unknown_py310 = onnxruntime_gpu_policy(
            cuda_info=CudaRuntimeInfo(source="test"),
            python_version=(3, 10),
        )
        self.assertEqual(unknown_py310.requirement, "onnxruntime-gpu>=1.21,<1.24")

        cuda13_py310 = onnxruntime_gpu_policy(
            cuda_info=CudaRuntimeInfo(major=13, minor=0, source="test"),
            python_version=(3, 10),
        )
        self.assertIn("Python >=3.11", cuda13_py310.error)

        cuda14 = onnxruntime_gpu_policy(
            cuda_info=CudaRuntimeInfo(major=14, minor=0, source="test"),
            python_version=(3, 13),
        )
        self.assertIn("does not yet have", cuda14.error)

    def test_cuda_runtime_detects_cudart_suffix_from_path(self):
        from backend.mathcraft.runtime_policy import detect_cuda_runtime

        root = ROOT / ".tmp_test_cuda_detect" / "bin"
        if root.parent.exists():
            shutil.rmtree(root.parent)
        self.addCleanup(
            lambda: shutil.rmtree(ROOT / ".tmp_test_cuda_detect", ignore_errors=True)
        )
        root.mkdir(parents=True)
        (root / "cudart64_110.dll").write_text("", encoding="utf-8")

        with mock.patch.dict(os.environ, {"PATH": str(root)}, clear=True):
            info = detect_cuda_runtime(use_nvcc=False)

        self.assertEqual(info.major, 11)
        self.assertEqual(info.source, "PATH:cudart")

    def test_cuda_diagnostics_uses_cuda11_dll_suffixes(self):
        from backend.mathcraft.cuda_diagnostics import diagnose_cuda_dll_paths
        from backend.mathcraft.runtime_policy import CudaRuntimeInfo

        root = ROOT / ".tmp_test_cuda_diag" / "CUDA" / "v11.8"
        if root.parent.parent.exists():
            shutil.rmtree(root.parent.parent)
        self.addCleanup(
            lambda: shutil.rmtree(ROOT / ".tmp_test_cuda_diag", ignore_errors=True)
        )
        bin_dir = root / "bin"
        bin_dir.mkdir(parents=True)
        for name in (
            "cudnn64_8.dll",
            "cudart64_110.dll",
            "cublas64_11.dll",
            "cublasLt64_11.dll",
            "cufft64_10.dll",
            "curand64_10.dll",
        ):
            (bin_dir / name).write_text("", encoding="utf-8")

        with mock.patch.dict(
            os.environ, {"CUDA_PATH": str(root), "PATH": str(bin_dir)}, clear=False
        ):
            report = diagnose_cuda_dll_paths(
                CudaRuntimeInfo(major=11, minor=8, source="test")
            )

        dll_names = [dll.name for dll in report.dlls]
        missing = [dll.name for dll in report.dlls if dll.missing_from_path]

        self.assertEqual(missing, [])
        self.assertIn("cudart64_110.dll", dll_names)
        self.assertIn("cudnn64_8.dll", dll_names)
        self.assertNotIn("cudart64_12.dll", dll_names)

    def test_cuda_shared_library_diagnostics_checks_linux_so_names(self):
        from backend.mathcraft.cuda_diagnostics import diagnose_cuda_shared_libraries

        root = ROOT / ".tmp_test_cuda_so_diag" / "lib64"
        if root.parent.exists():
            shutil.rmtree(root.parent)
        self.addCleanup(
            lambda: shutil.rmtree(ROOT / ".tmp_test_cuda_so_diag", ignore_errors=True)
        )
        root.mkdir(parents=True)
        for name in (
            "libcudart.so.12",
            "libcublas.so.12",
            "libcublasLt.so.12",
            "libcufft.so.11",
            "libcurand.so.10",
            "libcudnn.so.9",
        ):
            (root / name).write_text("", encoding="utf-8")

        with mock.patch.dict(os.environ, {"LD_LIBRARY_PATH": str(root)}, clear=True):
            report = diagnose_cuda_shared_libraries()

        missing = [item.name for item in report.libraries if item.missing]

        self.assertEqual(missing, [])
        self.assertIn("CUDA/cuDNN SO 检查", report.format_for_log())

    def test_pip_interrupted_leftovers_are_cleaned_from_target_site(self):
        from bootstrap import deps_runtime_verify

        with tempfile.TemporaryDirectory() as d:
            site = Path(d) / "site-packages"
            site.mkdir()
            leftover_dir = site / "~umpy"
            leftover_dist = site / "~ympy-1.14.0.dist-info"
            normal_dir = site / "numpy"
            leftover_dir.mkdir()
            leftover_dist.mkdir()
            normal_dir.mkdir()

            original = deps_runtime_verify._site_packages_root
            deps_runtime_verify._site_packages_root = lambda _pyexe: site
            try:
                removed = deps_runtime_verify._cleanup_pip_interrupted_leftovers(
                    Path(d) / "python.exe"
                )
            finally:
                deps_runtime_verify._site_packages_root = original

            self.assertEqual(removed, 2)
            self.assertFalse(leftover_dir.exists())
            self.assertFalse(leftover_dist.exists())
            self.assertTrue(normal_dir.exists())
