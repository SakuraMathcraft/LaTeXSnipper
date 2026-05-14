import threading
import os
import sys
from pathlib import Path
from utils import resource_path
import json
import queue
import re
import shutil
import subprocess
import time
import traceback

from backend.cuda_runtime_policy import (
    onnxruntime_cpu_spec,
    onnxruntime_gpu_policy,
    onnxruntime_gpu_spec,
)
from bootstrap.deps_python_runtime import (
    find_existing_python as _find_existing_python,
    find_local_python311_installer as _find_local_python311_installer_impl,
    find_system_python3 as _find_system_python3,
    inject_private_python_paths as _inject_private_python_paths,
    is_usable_python as _is_usable_python,
    normalize_deps_base_dir as _normalize_deps_base_dir,
    site_packages_root as _site_packages_root,
)
from bootstrap.deps_qt_compat import QIcon, QThread, QTimer, pyqtSignal
from bootstrap.deps_pip_runner import (
    PipInstallRunner,
    configure_pip_runner,
)
from bootstrap.deps_state import (
    load_json as _load_json,
    normalize_chosen_layers as _normalize_chosen_layers_impl,
    sanitize_state_layers as _sanitize_state_layers_impl,
    save_json as _save_json,
)
_LAST_ENSURE_DEPS_FORCE_ENTER = False


def was_last_ensure_deps_force_enter():
    return _LAST_ENSURE_DEPS_FORCE_ENTER


try:
    import psutil
except Exception:
    psutil = None

subprocess_lock = threading.Lock()


def _hidden_subprocess_kwargs() -> dict:
    if sys.platform != "win32":
        return {}
    kwargs = {"creationflags": int(getattr(subprocess, "CREATE_NO_WINDOW", 0))}
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        kwargs["startupinfo"] = startupinfo
    except Exception:
        pass
    return kwargs


def safe_run(cmd, cwd=None, shell=False, timeout=None, **popen_kwargs):
    """Start a subprocess and return the Popen object without eagerly reading stdout."""
    print(f"[RUN] {' '.join(cmd)}")

    popen_kwargs.setdefault("stdout", subprocess.PIPE)
    popen_kwargs.setdefault("stderr", subprocess.STDOUT)
    popen_kwargs.setdefault("text", True)
    for key, value in _hidden_subprocess_kwargs().items():
        popen_kwargs.setdefault(key, value)


    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        shell=shell,
        **popen_kwargs
    )
    return proc

class InstallWorker(QThread):
    log_updated = pyqtSignal(str)
    progress_updated = pyqtSignal(int)
    status_updated = pyqtSignal(str)
    busy_state_changed = pyqtSignal(bool)
    done = pyqtSignal(bool)

    def __init__(self, pyexe, pkgs, stop_event, pause_event, state_lock, state, state_path, chosen_layers, log_q,
                 mirror=False, force_reinstall=False, no_cache=False):
        super().__init__()
        self.mirror = mirror
        self.force_reinstall = force_reinstall
        self.no_cache = no_cache
        self._done_emitted = False
        self.proc = None
        self.pyexe = pyexe
        self.pkgs = pkgs
        self.stop_event = stop_event
        self.pause_event = pause_event
        self.state_lock = state_lock
        self.state = state
        self.state_path = state_path
        self.chosen_layers = chosen_layers
        self.log_q = log_q

    def _emit_done_safe(self, ok: bool):
        if not self._done_emitted:
            self._done_emitted = True
            try:
                self.busy_state_changed.emit(False)
            except RuntimeError:
                pass
            try:
                self.done.emit(ok)
            except RuntimeError:
                pass

    def stop(self):
        """Stop an install from the UI."""
        self.stop_event.set()
        if hasattr(self, "proc") and self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:
                pass
            finally:
                self.proc = None


    def run(self):
        """Main dependency install thread; MathCraft v1 only manages ONNX Runtime backends."""
        try:
            self.log_updated.emit(f"[INFO] 开始检查 {len(self.pkgs)} 个包...")
            self.log_updated.emit(f"[DEBUG] 使用 Python: {self.pyexe}")
            _cleanup_pip_interrupted_leftovers(self.pyexe, self.log_updated.emit)
            installed_before = _current_installed(self.pyexe)
            self.log_updated.emit(f"[INFO] 当前已安装 {len(installed_before)} 个包")
            if self.no_cache:
                self.log_updated.emit("[INFO] pip 缓存策略: 禁用缓存（--no-cache-dir）")
            else:
                self.log_updated.emit("[INFO] pip 缓存策略: 使用本地缓存（默认）")

            chosen_layers = _normalize_chosen_layers(self.chosen_layers or [])
            want_gpu_runtime = "MATHCRAFT_GPU" in chosen_layers
            want_cpu_runtime = "MATHCRAFT_CPU" in chosen_layers and not want_gpu_runtime

            if want_gpu_runtime and "onnxruntime" in installed_before:
                self.log_updated.emit("[INFO] 检测到 onnxruntime（CPU），将先卸载以避免与 onnxruntime-gpu 冲突...")
                self.log_updated.emit("[INFO] 注意：onnxruntime 和 onnxruntime-gpu 不能同时存在。")
                _uninstall_package_if_present(
                    self.pyexe,
                    "onnxruntime",
                    installed_map=installed_before,
                    log_fn=self.log_updated.emit,
                )
            elif want_cpu_runtime and "onnxruntime-gpu" in installed_before:
                self.log_updated.emit("[INFO] 检测到 onnxruntime-gpu，将先卸载以切换到 MathCraft CPU 后端...")
                self.log_updated.emit("[INFO] 注意：onnxruntime 和 onnxruntime-gpu 不能同时存在。")
                _uninstall_package_if_present(
                    self.pyexe,
                    "onnxruntime-gpu",
                    installed_map=installed_before,
                    log_fn=self.log_updated.emit,
                )

            def _resolve_layer_pkg_spec(pkg_spec: str) -> str:
                root_name = re.split(r'[<>=!~ ]', pkg_spec, 1)[0].strip().lower()
                if root_name == "onnxruntime":
                    return onnxruntime_cpu_spec(self.pyexe)
                if root_name == "onnxruntime-gpu":
                    return onnxruntime_gpu_spec(self.pyexe)
                return pkg_spec

            pending = []
            skipped = []
            if self.force_reinstall:
                pending = [_resolve_layer_pkg_spec(p) for p in self.pkgs]
                self.log_updated.emit("[INFO] 启用强制重装模式（忽略已安装包）")
            else:
                for p in self.pkgs:
                    effective_p = _resolve_layer_pkg_spec(p)
                    pkg_name = re.split(r'[<>=!~ ]', effective_p, 1)[0].lower()
                    if pkg_name in installed_before:
                        cur_ver = installed_before[pkg_name]
                        if _version_satisfies_spec(pkg_name, cur_ver, effective_p):
                            if pkg_name in ("onnxruntime", "onnxruntime-gpu"):
                                expect_gpu_ort = pkg_name == "onnxruntime-gpu"
                                ort_ok, ort_err = _verify_onnxruntime_runtime(
                                    self.pyexe, expect_gpu=expect_gpu_ort, timeout=20
                                )
                                if not ort_ok:
                                    pending.append(effective_p)
                                    self.log_updated.emit(
                                        f"[INFO] {pkg_name} 运行时异常，准备重装: {ort_err[:180]}"
                                    )
                                    continue
                            skipped.append(f"{pkg_name} ({cur_ver})")
                        else:
                            pending.append(effective_p)
                            self.log_updated.emit(
                                f"[INFO] {pkg_name} 版本不满足要求，准备重装: 当前 {cur_ver}，要求 {effective_p}"
                            )
                    else:
                        pending.append(effective_p)

            if skipped:
                self.log_updated.emit(f"[INFO] 跳过已安装: {', '.join(skipped[:10])}{'...' if len(skipped) > 10 else ''}")

            pending = _reorder_mathcraft_install_specs(pending, gpu_runtime_first=want_gpu_runtime)


            want_pandoc = "PANDOC" in chosen_layers

            if not pending:
                if want_pandoc:
                    self.log_updated.emit("[INFO] 所有 pip 依赖已安装，检查 pandoc...")
                    self.progress_updated.emit(20)
                else:
                    self.log_updated.emit("[INFO] 所有依赖已安装，无需下载。")
                    self.progress_updated.emit(80)
                    self._emit_done_safe(True)
                    return

            fail_count = 0
            failed_pkgs: list[str] = []
            pip_progress_max = 80
            total = len(pending)

            if pending:
                self.log_updated.emit(f"[INFO] 需要安装 {len(pending)} 个包（跳过 {len(skipped)} 个已安装）")

                done_count = 0
                fail_count = 0
                failed_pkgs = []

                pip_progress_max = 70 if want_pandoc else 80

                for idx, pkg in enumerate(pending, start=1):
                    while not self.pause_event.is_set():
                        if self.stop_event.is_set():
                            self.log_updated.emit("[CANCEL] 用户取消安装。")
                            break
                        time.sleep(0.1)
                    if self.stop_event.is_set():
                        self.log_updated.emit("[CANCEL] 用户取消安装。")
                        break

                    try:
                        pkg_label = re.split(r'[<>=!~ ]', pkg, 1)[0].strip()
                        self.status_updated.emit(f"正在安装第 {idx}/{total} 个包：{pkg_label}")
                        self.busy_state_changed.emit(True)
                        ok = _pip_install(
                            self.pyexe,
                            pkg,
                            self.stop_event,
                            self.log_q,
                            use_mirror=self.mirror,
                            flags=flags,
                            pause_event=self.pause_event,
                            force_reinstall=self.force_reinstall,
                            no_cache=self.no_cache,
                            proc_setter=lambda p: setattr(self, "proc", p),
                        )
                    except Exception as e:
                        ok = False
                        tb = traceback.format_exc()
                        self.log_updated.emit(f"[FATAL] 安装 {pkg} 时发生异常: {e}\n{tb}")
                    finally:
                        try:
                            self.busy_state_changed.emit(False)
                        except RuntimeError:
                            pass
                    done_count += 1
                    percent = int(done_count / total * pip_progress_max)
                    self.progress_updated.emit(percent)
                    if ok:
                        self.log_updated.emit(f"[OK] {pkg} 安装成功 ✅")
                    else:
                        self.log_updated.emit(f"[ERR] {pkg} 安装失败 ❌")
                        fail_count += 1
                        failed_pkgs.append(pkg)

                if self.stop_event.is_set():
                    self.log_updated.emit("[CANCEL] 安装已取消。")
                    self._emit_done_safe(False)
                    return


            pandoc_ok = True
            if want_pandoc:
                base_progress = pip_progress_max if pending else 20
                self.log_updated.emit("[PANDOC] 检查 pandoc 二进制文件...")

                def _pandoc_progress(pct: int):

                    mapped = base_progress + int((pct - 85) / 15.0 * (95 - base_progress))
                    self.progress_updated.emit(mapped)

                pandoc_ok = _ensure_pandoc_binary(
                    self.pyexe,
                    self.log_updated.emit,
                    progress_fn=_pandoc_progress,
                )

            _fix_critical_versions(self.pyexe, self.log_updated.emit, use_mirror=self.mirror)

            runtime_ort_ok = True
            runtime_ort_err = ""
            if want_gpu_runtime:
                runtime_ort_ok, runtime_ort_err = _repair_gpu_onnxruntime_runtime(
                    self.pyexe,
                    onnxruntime_gpu_spec(self.pyexe),
                    self.stop_event,
                    self.pause_event,
                    self.log_q,
                    use_mirror=self.mirror,
                    force_reinstall=self.force_reinstall,
                    no_cache=self.no_cache,
                    proc_setter=lambda p: setattr(self, "proc", p),
                )
                if not runtime_ort_ok:
                    self.log_updated.emit(f"[WARN] onnxruntime-gpu runtime still invalid: {runtime_ort_err[:400]}")
            elif want_cpu_runtime:
                runtime_ort_ok, runtime_ort_err = _verify_onnxruntime_runtime(
                    self.pyexe, expect_gpu=False, timeout=45
                )
                if not runtime_ort_ok:
                    self.log_updated.emit(f"[WARN] onnxruntime CPU runtime invalid: {runtime_ort_err[:400]}")

            all_ok = (fail_count == 0) and runtime_ort_ok and pandoc_ok

            if all_ok:
                self.log_updated.emit("[OK] 依赖安装阶段完成 ✅")
            elif fail_count == 0 and not runtime_ort_ok:
                self.log_updated.emit("[WARN] 包安装已完成（0 个安装失败），但 ONNX Runtime 验证失败 ❌")
                if runtime_ort_err:
                    self.log_updated.emit(f"[DIAG] {runtime_ort_err[:600]}")
                self.log_updated.emit("")
                self.log_updated.emit("💡 建议操作:")
                self.log_updated.emit("  1. 在依赖向导中仅选择 MATHCRAFT_CPU 或 MATHCRAFT_GPU 之一重装")
                self.log_updated.emit("  2. 如仍失败，先卸载 onnxruntime / onnxruntime-gpu 后再重装对应后端")
                self.log_updated.emit("  3. 确认没有混用系统 Python 与 deps\\python311 环境")
            else:
                self.log_updated.emit(f"[WARN] 部分安装失败，共 {fail_count}/{total} 个 ❌")
                self.log_updated.emit("")
                self.log_updated.emit("=" * 70)
                self.log_updated.emit("📋 失败包汇总 - 可在终端中手动安装:")
                self.log_updated.emit("")
                for pkg in failed_pkgs:
                    self.log_updated.emit(f'  pip install "{pkg}" --upgrade --user')
                self.log_updated.emit("")
                self.log_updated.emit("=" * 70)
                self.log_updated.emit("")
                self.log_updated.emit("🔍 常见失败原因及解决方案:")
                self.log_updated.emit("")
                self.log_updated.emit("  1. 🔒 程序占用文件：关闭本程序后再手动安装")
                self.log_updated.emit("  2. 🔐 权限不足：以管理员身份运行终端")
                self.log_updated.emit("  3. 🌐 网络问题：尝试使用镜像源或 VPN")
                self.log_updated.emit("  4. ⚠️ 依赖冲突：查看上方 [DIAG] 诊断信息")
                self.log_updated.emit("")
                self.log_updated.emit("💡 推荐操作:")
                self.log_updated.emit("  1. 关闭本程序")
                self.log_updated.emit("  2. 打开 CMD 终端（以管理员身份）")
                self.log_updated.emit("  3. 执行上述 pip install 命令")
                self.log_updated.emit("  4. 重新启动程序")
                self.log_updated.emit("=" * 70)

            self.progress_updated.emit(100)
            self._emit_done_safe(all_ok)
        except Exception as e:
            tb = traceback.format_exc()
            self.log_updated.emit(f"[FATAL] 安装线程未捕获异常: {e}\n{tb}")
            self._emit_done_safe(False)


class LayerVerifyWorker(QThread):
    log_updated = pyqtSignal(str)
    done = pyqtSignal(list, list)  # (ok_layers, fail_layers)

    def __init__(self, pyexe: str, chosen_layers: list, state_path):
        super().__init__()
        self.pyexe = pyexe
        self.chosen_layers = list(chosen_layers or [])
        self.state_path = state_path

    def run(self):
        verify_ok_layers = []
        verify_fail_layers = []
        for lyr in self.chosen_layers:
            v_ok, v_err = _verify_layer_runtime(self.pyexe, lyr, timeout=60)
            if v_ok:
                verify_ok_layers.append(lyr)
                self.log_updated.emit(f"  [OK] {lyr} 验证通过")
            else:
                verify_fail_layers.append(lyr)
                self.log_updated.emit(f"  [FAIL] {lyr} 验证失败:\n{(v_err or '')[:1000]}")
                for diag_line in _layer_verify_failure_diagnostics(lyr):
                    self.log_updated.emit(f"  [DIAG] {diag_line}")

        try:
            state = _load_json(self.state_path, {"installed_layers": []})
            current_layers = set(state.get("installed_layers", []))
            current_layers.update(verify_ok_layers)

            current_layers.difference_update(verify_fail_layers)

            if "MATHCRAFT_GPU" in verify_ok_layers:
                current_layers.discard("MATHCRAFT_CPU")
            elif "MATHCRAFT_CPU" in verify_ok_layers:
                current_layers.discard("MATHCRAFT_GPU")
            payload = {"installed_layers": sorted(list(current_layers))}
            payload["failed_layers"] = [layer for layer in verify_fail_layers if layer in LAYER_MAP] if verify_fail_layers else []
            _save_json(self.state_path, payload)
        except Exception as e:
            self.log_updated.emit(f"[WARN] 无法写入 .deps_state.json: {e}")

        self.done.emit(verify_ok_layers, verify_fail_layers)


class UninstallLayerWorker(QThread):
    log_updated = pyqtSignal(str)
    progress_updated = pyqtSignal(int)
    done = pyqtSignal(bool, str)  # success, layer_name

    def __init__(self, pyexe: str, state_path, layer_name: str, pkg_names: list[str]):
        super().__init__()
        self.pyexe = str(pyexe)
        self.state_path = Path(state_path)
        self.layer_name = str(layer_name)
        self.pkg_names = [str(x) for x in (pkg_names or []) if str(x).strip()]

    def run(self):
        ok = True
        total = max(len(self.pkg_names), 1)
        self.log_updated.emit(f"[STEP] 开始卸载层 {self.layer_name} ...")
        self.progress_updated.emit(5)
        for idx, pkg_name in enumerate(self.pkg_names, start=1):
            self.log_updated.emit(f"[CMD] {self.pyexe} -m pip uninstall -y {pkg_name}")
            try:
                result = subprocess.run(
                    [self.pyexe, "-m", "pip", "uninstall", "-y", pkg_name],
                    check=False,
                    capture_output=True,
                    text=True,
                    creationflags=flags
                )
                output = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
                if output:
                    for line in output.splitlines():
                        self.log_updated.emit(line.rstrip())
                if result.returncode == 0:
                    self.log_updated.emit(f"[OK] {pkg_name} 卸载完成")
                else:
                    ok = False
                    self.log_updated.emit(f"[WARN] {pkg_name} 卸载返回码={result.returncode}")
            except Exception as e:
                ok = False
                self.log_updated.emit(f"[ERR] {pkg_name} 卸载失败: {e}")
            self.progress_updated.emit(5 + int(75 * idx / total))

        if any(str(name).lower().startswith("onnxruntime") for name in self.pkg_names):
            _cleanup_orphan_onnxruntime_namespace(self.pyexe, log_fn=self.log_updated.emit)


        if any(str(name).lower() in {"pypandoc", "pandoc"} for name in self.pkg_names):
            self.log_updated.emit("[PANDOC] pip 包已卸载，正在清理 pandoc 二进制和残留文件...")
            _cleanup_pandoc_leftovers(log_fn=self.log_updated.emit)

            pandoc_dir = _pandoc_data_dir()
            if pandoc_dir.exists():
                try:
                    import shutil as _shutil
                    _shutil.rmtree(pandoc_dir, ignore_errors=True)
                    self.log_updated.emit(f"[PANDOC] 已删除目录: {pandoc_dir}")
                except Exception as e:
                    self.log_updated.emit(f"[PANDOC] 删除目录失败: {e}")

            pandoc_dir_str = str(pandoc_dir)
            current_path = os.environ.get("PATH", "")
            if pandoc_dir_str in current_path:
                os.environ["PATH"] = current_path.replace(pandoc_dir_str + os.pathsep, "").replace(os.pathsep + pandoc_dir_str, "").replace(pandoc_dir_str, "")
                self.log_updated.emit("[PANDOC] 已从 PATH 中移除 deps/pandoc")
            try:
                from runtime.pandoc_runtime import clear_configured_pandoc_path
                clear_configured_pandoc_path()
                self.log_updated.emit("[PANDOC] 已清理持久化路径配置")
            except Exception:
                pass

        try:
            data = {"installed_layers": []}
            if self.state_path.exists():
                with open(self.state_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    data = loaded
            layers = [str(x) for x in data.get("installed_layers", []) if str(x) != self.layer_name]
            failed = [str(x) for x in data.get("failed_layers", []) if str(x) != self.layer_name]
            payload = {"installed_layers": layers}
            if failed:
                payload["failed_layers"] = failed
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            self.log_updated.emit(f"[OK] 状态文件已更新，移除层 {self.layer_name}")
        except Exception as e:
            ok = False
            self.log_updated.emit(f"[ERR] 状态文件更新失败: {e}")

        self.progress_updated.emit(100)
        self.done.emit(ok, self.layer_name)

os.environ["PYTHONUTF8"] = "1"

flags = 0
if sys.platform == "win32":

    flags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
CONFIG_FILE = "LaTeXSnipper_config.json"
STATE_FILE = ".deps_state.json"


def _config_dir_path() -> Path:
    p = Path.home() / ".latexsnipper"
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return p

ORT_CPU_SPEC = "onnxruntime"
ORT_GPU_DEFAULT_SPEC = "onnxruntime-gpu"
pip_ready_event = threading.Event()
PIP_INSTALL_SUPPRESS_ARGS = ["--no-warn-script-location"]
configure_pip_runner(
    safe_run=safe_run,
    subprocess_lock=subprocess_lock,
    suppress_args=PIP_INSTALL_SUPPRESS_ARGS,
)

CRITICAL_VERSIONS = {
    "numpy": "numpy>=1.26,<3",
    "sympy": "sympy>=1.13,<1.15",
    "flatbuffers": "flatbuffers>=24.3.25",
    "packaging": "packaging>=23",
    "coloredlogs": "coloredlogs>=15.0.1",
    "rapidocr": "rapidocr==3.5.0",
    "protobuf": "protobuf>=3.20,<5",
}

RUNTIME_IMPORT_CHECKS = {
    "numpy": "numpy",
    "sympy": "sympy",
    "flatbuffers": "flatbuffers",
    "packaging": "packaging",
    "coloredlogs": "coloredlogs",
    "protobuf": "google.protobuf",
}


def _cleanup_pip_interrupted_leftovers(pyexe: str | Path, log_fn=None) -> int:
    """Remove pip's half-uninstalled '~pkg' leftovers from the target site-packages."""
    try:
        site_packages = _site_packages_root(Path(pyexe))
    except Exception:
        site_packages = None
    if not site_packages or not site_packages.exists():
        return 0

    removed: list[str] = []
    for item in site_packages.iterdir():
        if not item.name.startswith("~"):
            continue
        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
            removed.append(item.name)
        except Exception as e:
            if log_fn:
                log_fn(f"  [WARN] 清理 pip 残留失败 {item.name}: {e}")

    if removed and log_fn:
        shown = ", ".join(removed[:8])
        suffix = "..." if len(removed) > 8 else ""
        log_fn(f"[INFO] 已清理 pip 中断残留: {shown}{suffix}")
    return len(removed)


def _cleanup_orphan_onnxruntime_namespace(
    pyexe: str | Path,
    installed_map: dict | None = None,
    log_fn=None,
) -> int:
    """
    Remove an onnxruntime package directory left behind without pip metadata.

    pip cannot uninstall this state because no onnxruntime*.dist-info exists,
    but Python still imports the namespace and then misses get_available_providers.
    """
    current = installed_map if installed_map is not None else _current_installed(pyexe)
    if "onnxruntime" in current or "onnxruntime-gpu" in current:
        return 0
    try:
        site_packages = _site_packages_root(Path(pyexe))
    except Exception:
        site_packages = None
    if not site_packages or not site_packages.exists():
        return 0

    target = site_packages / "onnxruntime"
    if not target.exists():
        return 0
    try:
        if not target.resolve().is_relative_to(site_packages.resolve()):
            return 0
    except Exception:
        return 0

    try:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    except Exception as e:
        if log_fn:
            log_fn(f"[WARN] 清理 onnxruntime 孤儿目录失败: {e}")
        return 0

    if log_fn:
        log_fn(f"[INFO] 已清理未被 pip 管理的 onnxruntime 残留目录: {target}")
    return 1


def _verify_runtime_support_imports(pyexe: str, timeout: int = 30) -> tuple[bool, str]:
    """Verify core imports that ONNX Runtime relies on after pip repair."""
    code = (
        "import importlib, json, traceback\n"
        f"mods = {json.dumps(RUNTIME_IMPORT_CHECKS, ensure_ascii=False)}\n"
        "bad = []\n"
        "for pkg, mod in mods.items():\n"
        " try:\n"
        "  importlib.import_module(mod)\n"
        " except BaseException as e:\n"
        "  bad.append({'pkg': pkg, 'module': mod, 'err': f'{type(e).__name__}: {e}', 'traceback': traceback.format_exc()[-1200:]})\n"
        "print(json.dumps({'ok': not bad, 'bad': bad}, ensure_ascii=False))\n"
    )
    try:
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        result = subprocess.run(
            [str(pyexe), "-c", code],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        raw = "\n".join([(result.stdout or ""), (result.stderr or "")]).strip()
        payload = None
        for line in reversed(raw.splitlines()):
            s = line.strip()
            if s.startswith("{") and s.endswith("}"):
                try:
                    payload = json.loads(s)
                    break
                except Exception:
                    pass
        if not isinstance(payload, dict):
            return False, f"runtime dependency check no json output: {raw[:400]}"
        if payload.get("ok"):
            return True, ""
        bad = payload.get("bad") or []
        if bad:
            first = bad[0]
            return False, f"{first.get('pkg')}: {first.get('err') or 'unknown'}"
        return False, "runtime dependency check failed: unknown"
    except subprocess.TimeoutExpired:
        return False, "runtime dependency check timeout"
    except Exception as e:
        return False, str(e)


def _force_repair_broken_runtime_imports(
    pyexe: str,
    log_fn=None,
    use_mirror: bool = False,
    max_rounds: int = 4,
) -> tuple[bool, str]:
    """Force-reinstall only the runtime support package whose import is actually broken."""
    last_err = ""
    for _ in range(max_rounds):
        ok, err = _verify_runtime_support_imports(pyexe)
        if ok:
            return True, ""
        last_err = err
        pkg = (err.split(":", 1)[0] if err else "").strip().lower()
        spec = CRITICAL_VERSIONS.get(pkg)
        if not spec:
            return False, err

        if log_fn:
            log_fn(f"  [WARN] {pkg} 导入失败，定点强制修复: {err[:240]}")
        cmd = [
            str(pyexe),
            "-m",
            "pip",
            "install",
            spec,
            "--upgrade",
            "--force-reinstall",
            "--no-deps",
            *PIP_INSTALL_SUPPRESS_ARGS,
        ]
        if use_mirror:
            cmd += ["-i", "https://pypi.tuna.tsinghua.edu.cn/simple"]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=240,
                creationflags=flags,
            )
            if result.returncode != 0:
                raw = (result.stderr or result.stdout or "").strip().replace("\r", "")
                if log_fn:
                    log_fn(f"  [WARN] 强制修复 {pkg} 失败: {raw[:400]}")
                return False, raw[:400] or err
            if log_fn:
                log_fn(f"  [OK] 已强制修复 {pkg}")
        except subprocess.TimeoutExpired:
            return False, f"{pkg} force repair timeout"
        except Exception as e:
            return False, str(e)

    ok, err = _verify_runtime_support_imports(pyexe)
    return ok, err or last_err


def _ensure_pandoc_binary(pyexe: str, log_fn=None, progress_fn=None) -> bool:
    """Ensure the pandoc executable is available."""
    if log_fn:
        log_fn("[PANDOC] 正在检查 pandoc 二进制文件...")


    import shutil as _shutil

    def _resolve_pandoc_exe() -> str | None:
        """Return the persisted or dependency-managed pandoc executable path first."""
        try:
            from runtime.pandoc_runtime import load_configured_pandoc_path
            configured = load_configured_pandoc_path()
            if configured is not None:
                return str(configured)
        except Exception:
            pass
        deps_dir = Path.cwd() / "deps" / "pandoc"
        if deps_dir.is_dir():
            for name in ("pandoc.exe", "pandoc"):
                p = deps_dir / name
                if p.exists() and p.is_file():
                    return str(p)
        return _shutil.which("pandoc")

    pandoc_exe = _resolve_pandoc_exe()
    if pandoc_exe:
        current_ver = _get_pandoc_version(pandoc_exe)
        if current_ver and not _pandoc_version_too_old(current_ver, _PANDOC_VERSION):
            if log_fn:
                log_fn(f"[PANDOC] pandoc 已就绪 (v{'.'.join(str(x) for x in current_ver)})，跳过下载 ✅")
            try:
                from runtime.pandoc_runtime import save_configured_pandoc_path
                save_configured_pandoc_path(pandoc_exe)
            except Exception:
                pass
            _cleanup_pandoc_leftovers(log_fn)
            return True
        if log_fn:
            if current_ver:
                log_fn(f"[PANDOC] 检测到 pandoc v{'.'.join(str(x) for x in current_ver)} < v{_PANDOC_VERSION}，尝试更新...")
            else:
                log_fn("[PANDOC] 检测到 pandoc 但无法读取版本，尝试更新...")


    _cleanup_pandoc_leftovers(log_fn)
    if log_fn:
        log_fn("[PANDOC] 从镜像下载 pandoc 二进制...")
    if progress_fn:
        progress_fn(85)
    ok = _download_pandoc_from_mirrors(log_fn)
    if ok:
        if log_fn:
            log_fn("[PANDOC] pandoc 二进制文件就绪 ✅")
        if progress_fn:
            progress_fn(100)
        _cleanup_pandoc_leftovers(log_fn)
        return True

    if log_fn:
        log_fn("[PANDOC] pandoc 二进制文件下载失败")
        log_fn("[PANDOC] 请手动安装：https://github.com/jgm/pandoc/releases")
        if sys.platform == "win32":
            log_fn("[PANDOC] 或运行: winget install JohnMacFarlane.Pandoc")
        elif sys.platform == "linux":
            log_fn("[PANDOC] 或运行: sudo apt install pandoc / sudo dnf install pandoc")
        elif sys.platform == "darwin":
            log_fn("[PANDOC] 或运行: brew install pandoc")
    if progress_fn:
        progress_fn(100)
    return False


def _cleanup_pandoc_leftovers(log_fn=None) -> None:
    """Clean stale pandoc binaries that do not belong to the current platform."""
    import time as _time

    removed_count = 0

    def _safe_unlink(filepath: Path, label: str) -> bool:
        """Delete a file safely with retries and delayed-delete fallback on Windows."""
        nonlocal removed_count
        for attempt in range(3):
            try:
                filepath.unlink()
                removed_count += 1
                if log_fn:
                    log_fn(f"[PANDOC] 已清理{label}: {filepath.name}")
                return True
            except PermissionError:
                if attempt < 2:
                    _time.sleep(0.5)
                    continue

                if sys.platform == "win32":
                    try:
                        import ctypes
                        ctypes.windll.kernel32.MoveFileExW(
                            str(filepath), None, 4  # MOVEFILE_DELAY_UNTIL_REBOOT = 4
                        )
                        removed_count += 1
                        if log_fn:
                            log_fn(f"[PANDOC] 已标记重启后删除{label}: {filepath.name}")
                        return True
                    except Exception:
                        pass
                if log_fn:
                    log_fn(f"[PANDOC] 清理{label}失败(占用): {filepath.name}")
                return False
            except Exception as e:
                if log_fn:
                    log_fn(f"[PANDOC] 清理{label}失败: {filepath.name} ({e})")
                return False
        return False


    pandoc_dir = _pandoc_data_dir()
    if pandoc_dir.is_dir():
        try:
            _bin_name = _pandoc_platform_archive()[1]
        except Exception:
            _bin_name = None
        for stale in pandoc_dir.iterdir():
            if stale.is_file() and stale.name.startswith("pandoc"):
                if _bin_name and stale.name == _bin_name:
                    continue
                _safe_unlink(stale, "旧二进制")

    if removed_count > 0 and log_fn:
        log_fn(f"[PANDOC] 共清理 {removed_count} 个无用文件")


def _get_pandoc_version(pandoc_path: str | None = None) -> tuple[int, ...] | None:
    """Return the installed pandoc version."""
    import shutil as _shutil
    exe = pandoc_path or _shutil.which("pandoc")
    if not exe:

        try:
            deps_dir = Path.cwd() / "deps" / "pandoc"
            for candidate in ("pandoc.exe", "pandoc"):
                cand_path = deps_dir / candidate
                if cand_path.exists():
                    exe = str(cand_path)
                    break
        except Exception:
            pass
    if not exe:
        return None

    try:
        result = subprocess.run(
            [str(exe), "--version"],
            capture_output=True, text=True, timeout=10,
            creationflags=flags if sys.platform == "win32" else 0,
        )
        if result.returncode != 0:
            return None

        first_line = (result.stdout or "").splitlines()[0].strip()
        parts = first_line.split()
        for part in parts:
            stripped = part.strip().rstrip(",")
            if stripped and stripped[0].isdigit():
                return tuple(int(x) for x in stripped.split("."))
    except Exception:
        pass
    return None


def _pandoc_version_too_old(current: tuple[int, ...] | None, target: str) -> bool:
    """Return whether the current pandoc version is older than the target version."""
    if current is None:
        return True
    target_tuple = tuple(int(x) for x in target.split("."))
    return current < target_tuple



_PANDOC_VERSION = "3.9.0.2"


def _pandoc_platform_archive() -> tuple[str, str, str]:
    """Return the archive filename, binary name, and archive type for this platform."""
    import platform as _plt
    system = _plt.system()
    machine = _plt.machine()

    if system == "Windows" and machine in ("AMD64", "x86_64"):
        return (
            f"pandoc-{_PANDOC_VERSION}-windows-x86_64.zip",
            "pandoc.exe",
            "zip",
        )
    if system == "Linux" and machine in ("x86_64", "AMD64"):
        return (
            f"pandoc-{_PANDOC_VERSION}-linux-amd64.tar.gz",
            "pandoc",
            "tar.gz",
        )
    if system == "Darwin":
        if machine == "arm64":
            return (
                f"pandoc-{_PANDOC_VERSION}-arm64-macOS.zip",
                "pandoc",
                "zip",
            )
        if machine in ("x86_64", "AMD64"):
            return (
                f"pandoc-{_PANDOC_VERSION}-x86_64-macOS.zip",
                "pandoc",
                "zip",
            )

    raise RuntimeError(
        f"[PANDOC] 不支持的平台: {system} {machine}，请手动安装 pandoc"
    )


def _build_pandoc_mirrors() -> list[str]:
    """Build pandoc mirror URLs for the current platform."""
    archive_name, _bin_name, _arc_type = _pandoc_platform_archive()
    return [

        f"https://ghfast.top/https://github.com/jgm/pandoc/releases/download/{_PANDOC_VERSION}/{archive_name}",
        f"https://gh-proxy.com/https://github.com/jgm/pandoc/releases/download/{_PANDOC_VERSION}/{archive_name}",

        f"https://github.com/jgm/pandoc/releases/download/{_PANDOC_VERSION}/{archive_name}",
    ]


def _rank_mirrors_by_speed(mirrors: list[str], log_fn=None) -> list[str]:
    """Rank mirrors by HEAD request latency."""
    import urllib.request
    import time as _time

    results: list[tuple[float, str]] = []
    for url in mirrors:
        short = url[:70]
        try:
            req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "LaTeXSnipper"})
            t0 = _time.monotonic()
            resp = urllib.request.urlopen(req, timeout=8)
            resp.close()
            latency = _time.monotonic() - t0
            results.append((latency, url))
            if log_fn:
                log_fn(f"[PANDOC] 延迟测试 {short}... → {latency:.1f}s")
        except Exception as e:
            if log_fn:
                log_fn(f"[PANDOC] 延迟测试 {short}... → 失败 ({str(e)[:60]})")
            continue

    if not results:
        return mirrors

    results.sort(key=lambda x: x[0])
    ranked = [url for _, url in results]
    if log_fn:
        log_fn(f"[PANDOC] 最快镜像: {ranked[0][:70]}...")
    return ranked


def _download_pandoc_from_mirrors(log_fn=None) -> bool:
    """Download pandoc from mirrors and extract it into deps/pandoc."""
    import urllib.request
    import time as _time

    try:
        archive_name, binary_name, archive_type = _pandoc_platform_archive()
    except RuntimeError as e:
        if log_fn:
            log_fn(f"[PANDOC] {e}")
        return False

    pandoc_dir = _pandoc_data_dir()
    pandoc_dir.mkdir(parents=True, exist_ok=True)

    mirrors = _build_pandoc_mirrors()
    if log_fn:
        log_fn(f"[PANDOC] 平台归档: {archive_name} ({archive_type})")
        log_fn(f"[PANDOC] 共 {len(mirrors)} 个镜像源，正在测速选择最快...")


    mirrors = _rank_mirrors_by_speed(mirrors, log_fn)

    for idx, url in enumerate(mirrors, start=1):
        if log_fn:
            log_fn(f"[PANDOC] [{idx}/{len(mirrors)}] 尝试: {url[:80]}...")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "LaTeXSnipper"})
            resp = urllib.request.urlopen(req, timeout=30)
            total = int(resp.headers.get("Content-Length", 0))
            if log_fn and total > 0:
                log_fn(f"[PANDOC] 文件大小: {total // 1024} KB")


            chunks: list[bytes] = []
            downloaded = 0
            last_log_time = _time.monotonic()
            last_log_bytes = 0
            chunk_size = 64 * 1024  # 64 KB

            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                chunks.append(chunk)
                downloaded += len(chunk)

                now = _time.monotonic()
                elapsed = now - last_log_time
                if elapsed >= 2.0:
                    speed = (downloaded - last_log_bytes) / elapsed / 1024  # KB/s
                    if total > 0:
                        pct = downloaded * 100 // total
                        if log_fn:
                            log_fn(f"[PANDOC] 下载中: {pct}%  ({downloaded // 1024}/{total // 1024} KB)  {speed:.0f} KB/s")
                    else:
                        if log_fn:
                            log_fn(f"[PANDOC] 下载中: {downloaded // 1024} KB  {speed:.0f} KB/s")
                    last_log_time = now
                    last_log_bytes = downloaded

            resp.close()
            data = b"".join(chunks)

            if len(data) < 100_000:
                if log_fn:
                    log_fn(f"[PANDOC] 响应过小 ({len(data)} bytes)，跳过此镜像")
                continue

            if log_fn:
                log_fn(f"[PANDOC] 下载完成 ({len(data) // 1024} KB)，正在解压 ({archive_type})...")


            exe_data = _extract_pandoc_binary(data, archive_type, binary_name, log_fn)
            if exe_data is None:
                if log_fn:
                    log_fn(f"[PANDOC] 归档中未找到 {binary_name}")
                continue

            exe_path = pandoc_dir / binary_name
            exe_path.write_bytes(exe_data)
            if log_fn:
                log_fn(f"[PANDOC] 已写入: {exe_path}")


            if sys.platform != "win32":
                try:
                    os.chmod(str(exe_path), 0o755)
                except Exception:
                    pass


            dir_str = str(pandoc_dir)
            if dir_str not in os.environ.get("PATH", ""):
                os.environ["PATH"] = dir_str + os.pathsep + os.environ.get("PATH", "")


            verify_cmd = [str(exe_path), "--version"]
            result = subprocess.run(
                verify_cmd,
                capture_output=True, text=True, timeout=10,
                creationflags=flags if sys.platform == "win32" else 0,
            )
            if result.returncode == 0:
                ver_line = (result.stdout or "").splitlines()[0]
                try:
                    from runtime.pandoc_runtime import save_configured_pandoc_path
                    save_configured_pandoc_path(exe_path)
                except Exception:
                    pass
                if log_fn:
                    log_fn(f"[PANDOC] 验证通过: {ver_line}")
                return True

        except Exception as e:
            if log_fn:
                log_fn(f"[PANDOC] 失败: {str(e)[:120]}")
            continue

    return False


def _extract_pandoc_binary(
    data: bytes,
    archive_type: str,
    binary_name: str,
    log_fn=None,
) -> bytes | None:
    """Extract the pandoc executable from archive bytes."""
    import io
    import zipfile

    if archive_type == "zip":
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for member in zf.namelist():
                if member.endswith(binary_name):
                    return zf.read(member)
        return None

    if archive_type == "tar.gz":
        import tarfile
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
            for member in tf.getmembers():
                if member.name.endswith(binary_name) and member.isfile():
                    f = tf.extractfile(member)
                    if f:
                        return f.read()
        return None

    if log_fn:
        log_fn(f"[PANDOC] 不支持的归档类型: {archive_type}")
    return None


def _pandoc_data_dir() -> Path:
    """Return the dependency-managed pandoc binary directory."""

    cwd = Path.cwd()
    venv_candidate = cwd / ".venv"
    if venv_candidate.is_dir():
        base = cwd
    else:

        base = cwd
    target = base / "deps" / "pandoc"
    return target


def _fix_critical_versions(pyexe: str, log_fn=None, use_mirror: bool = False) -> bool:
    """Force critical dependency versions after installation."""
    import subprocess

    if log_fn:
        log_fn("[INFO] 正在修复关键依赖版本...")

    _cleanup_pip_interrupted_leftovers(pyexe, log_fn)

    installed_before = _current_installed(pyexe)

    for pkg, spec in CRITICAL_VERSIONS.items():
        try:
            cur = installed_before.get(pkg)
            if cur and _version_satisfies_spec(pkg, cur, spec):
                continue

            cmd = [str(pyexe), "-m", "pip", "install", spec, "--upgrade", "--no-deps", *PIP_INSTALL_SUPPRESS_ARGS]
            if use_mirror:
                cmd += ["-i", "https://pypi.tuna.tsinghua.edu.cn/simple"]
            timeout_sec = 180
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec, creationflags=flags)
            if log_fn:
                if result.returncode == 0:
                    log_fn(f"  [OK] 已修复 {pkg} → {spec.split('==')[-1] if '==' in spec else spec}")
                else:
                    err = (result.stderr or result.stdout or "").strip().replace("\r", "")
                    log_fn(f"  [WARN] 修复 {pkg} 失败: {err[:240]}")
        except subprocess.TimeoutExpired:
            if log_fn:
                log_fn(f"  [WARN] 修复 {pkg} 超时，已跳过")
        except Exception as e:
            if log_fn:
                log_fn(f"  [WARN] 修复 {pkg} 异常: {e}")

    if log_fn:
        log_fn("[INFO] 关键版本修复完成")

    ok, err = _verify_runtime_support_imports(pyexe)
    if not ok:
        ok, err = _force_repair_broken_runtime_imports(
            pyexe,
            log_fn=log_fn,
            use_mirror=use_mirror,
        )
    if log_fn:
        if ok:
            log_fn("[OK] ONNX Runtime 支撑依赖导入检查通过（numpy/protobuf 等）")
        else:
            log_fn(f"[WARN] ONNX Runtime 关键依赖仍不可用: {err[:400]}")
    return ok


_CORE_VERIFY_CODE = """
import importlib.util

for mod in ("transformers", "rapidocr", "cv2", "PIL", "latex2mathml.converter", "matplotlib", "fitz"):
    if importlib.util.find_spec(mod) is None:
        raise RuntimeError(f"{mod} not installed")

print("CORE OK")
"""


def _onnxruntime_session_verify_code(*, expect_gpu: bool) -> str:
    expected_provider = "CUDAExecutionProvider" if expect_gpu else "CPUExecutionProvider"
    requested_providers = (
        "['CUDAExecutionProvider', 'CPUExecutionProvider']"
        if expect_gpu
        else "['CPUExecutionProvider']"
    )
    layer_name = "MATHCRAFT_GPU" if expect_gpu else "MATHCRAFT_CPU"
    return f"""
import onnxruntime as ort


def _varint(value):
    out = []
    value = int(value)
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            break
    return bytes(out)


def _key(field, wire_type):
    return _varint((int(field) << 3) | int(wire_type))


def _int_field(field, value):
    return _key(field, 0) + _varint(value)


def _str_field(field, value):
    raw = str(value).encode("utf-8")
    return _key(field, 2) + _varint(len(raw)) + raw


def _msg_field(field, payload):
    return _key(field, 2) + _varint(len(payload)) + payload


def _minimal_identity_onnx():
    dim = _int_field(1, 1)
    shape = _msg_field(1, dim)
    tensor_type = _int_field(1, 1) + _msg_field(2, shape)
    type_proto = _msg_field(1, tensor_type)
    value_x = _str_field(1, "x") + _msg_field(2, type_proto)
    value_y = _str_field(1, "y") + _msg_field(2, type_proto)
    node = _str_field(1, "x") + _str_field(2, "y") + _str_field(4, "Identity")
    graph = _msg_field(1, node) + _str_field(2, "g") + _msg_field(11, value_x) + _msg_field(12, value_y)
    opset = _int_field(2, 13)
    return _int_field(1, 8) + _str_field(2, "latexsnipper-check") + _msg_field(7, graph) + _msg_field(8, opset)


providers = list(ort.get_available_providers() or [])
expected = "{expected_provider}"
if expected not in providers:
    raise RuntimeError(f"{{expected}} unavailable: {{providers}}")

session = ort.InferenceSession(_minimal_identity_onnx(), providers={requested_providers})
actual = list(session.get_providers() or [])
if expected not in actual:
    raise RuntimeError(
        f"{{expected}} listed but failed to initialize an ONNX session; "
        f"available={{providers}}, session={{actual}}"
    )

print("ONNX providers:", providers)
print("ONNX session providers:", actual)
print("{layer_name} OK")
"""


LAYER_VERIFY_CODE = {
    "BASIC": """
import PIL
import requests
import lxml
print("BASIC OK")
""",
    "CORE": _CORE_VERIFY_CODE,
    "MATHCRAFT_CPU": _onnxruntime_session_verify_code(expect_gpu=False),
    "MATHCRAFT_GPU": _onnxruntime_session_verify_code(expect_gpu=True),
    "PANDOC": """
import importlib.util, shutil, os, sys
if importlib.util.find_spec("pypandoc") is None:
    raise RuntimeError("pypandoc not installed")
configured_pandoc = None
try:
    import json
    from pathlib import Path
    cfg_path = Path.home() / ".latexsnipper" / "LaTeXSnipper_config.json"
    if cfg_path.exists():
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        raw = str(cfg.get("pandoc_executable_path", "") or "").strip() if isinstance(cfg, dict) else ""
        if raw:
            path = Path(raw).expanduser()
            configured_pandoc = path if path.is_file() else None
except Exception:
    configured_pandoc = None
if configured_pandoc is not None:
    deps_dir = str(configured_pandoc.parent)
    if deps_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = deps_dir + os.pathsep + os.environ.get("PATH", "")
# Also check deps/pandoc.
deps_pandoc = os.path.join(os.path.dirname(sys.executable), "pandoc")
if os.path.isdir(deps_pandoc) and deps_pandoc not in os.environ.get("PATH", ""):
    os.environ["PATH"] = deps_pandoc + os.pathsep + os.environ.get("PATH", "")
if not shutil.which("pandoc"):
    raise RuntimeError("pandoc binary not found (pypandoc is installed but pandoc executable is missing)")
print("PANDOC OK")
""",
}


def _verify_layer_runtime(pyexe: str, layer: str, timeout: int = 60) -> tuple:
    """Verify whether a feature layer works at runtime."""
    import subprocess

    if layer == "CORE":
        timeout = max(timeout, 120)

    if layer in LAYER_VERIFY_CODE:
        code = LAYER_VERIFY_CODE[layer]
    else:

        return True, ""

    try:
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        result = subprocess.run(
            [pyexe, "-c", code],
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )
        if result.returncode == 0:
            return True, ""
        else:

            err = (result.stderr or result.stdout or "").strip()
            if not err:
                err = f"验证进程返回码 {result.returncode}，但无可用输出"

            err_lines = err.replace("\r", "").split('\n')[-15:]
            return False, '\n'.join(err_lines)
    except subprocess.TimeoutExpired:
        return False, "验证超时"
    except Exception as e:
        return False, str(e)


def _layer_verify_failure_diagnostics(layer: str) -> list[str]:
    if layer != "MATHCRAFT_GPU":
        return []
    try:
        from backend.cuda_diagnostics import diagnose_cuda_dll_paths

        report = diagnose_cuda_dll_paths()
        return [report.format_for_user(), report.format_for_log()]
    except Exception as e:
        return [f"CUDA/cuDNN DLL 诊断失败: {e}"]


def _verify_installed_layers(pyexe: str, claimed_layers: list, log_fn=None) -> list:
    """Verify all installed layers and return the layers that pass."""
    verified = []
    for layer in claimed_layers:
        ok, err = _verify_layer_runtime(pyexe, layer)
        if ok:
            verified.append(layer)
            if log_fn:
                log_fn(f"[OK] {layer} 层验证通过")
        else:
            if log_fn:
                log_fn(f"[WARN] {layer} 层验证失败: {err[:200]}")
                for diag_line in _layer_verify_failure_diagnostics(layer):
                    log_fn(f"[DIAG] {diag_line}")
    return verified



def _verify_onnxruntime_runtime(pyexe: str, expect_gpu: bool = False, timeout: int = 30) -> tuple[bool, str]:
    """Verify that ONNX Runtime imports and exposes the expected backend."""
    code = (
        "import json, traceback\n"
        "out = {'ok': False, 'file': '', 'has_func': False, 'providers': [], 'err': ''}\n"
        "try:\n"
        " import onnxruntime as ort\n"
        " out['file'] = str(getattr(ort, '__file__', '') or '')\n"
        " out['has_func'] = bool(hasattr(ort, 'get_available_providers'))\n"
        " if out['has_func']:\n"
        "  out['providers'] = list(ort.get_available_providers() or [])\n"
        " out['ok'] = True\n"
        "except BaseException as e:\n"
        " out['err'] = f'{type(e).__name__}: {e}'\n"
        " out['traceback'] = traceback.format_exc()[-1600:]\n"
        "print(json.dumps(out, ensure_ascii=False))\n"
    )
    try:
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        result = subprocess.run(
            [str(pyexe), "-c", code],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        raw = "\n".join([(result.stdout or ""), (result.stderr or "")]).strip()
        payload = None
        for line in reversed(raw.splitlines()):
            s = line.strip()
            if not s:
                continue
            if s.startswith("{") and s.endswith("}"):
                try:
                    payload = json.loads(s)
                    break
                except Exception:
                    pass
        if not isinstance(payload, dict):
            return False, f"onnxruntime check no json output: {raw[:240]}"
        if not payload.get("ok"):
            detail = payload.get("err") or payload.get("traceback") or "unknown"
            return False, f"onnxruntime import failed: {str(detail)[:400]}"
        if not payload.get("has_func"):
            return False, "onnxruntime missing get_available_providers (broken namespace package)"
        providers = payload.get("providers") or []
        if expect_gpu and "CUDAExecutionProvider" not in providers:
            return False, f"CUDAExecutionProvider unavailable: {providers}"
        if not expect_gpu and "CPUExecutionProvider" not in providers:
            return False, f"CPUExecutionProvider unavailable: {providers}"
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "onnxruntime check timeout"
    except Exception as e:
        return False, str(e)


def _uninstall_package_if_present(pyexe: str, pkg_name: str, installed_map: dict | None = None,
                                  log_fn=None, timeout: int = 120) -> bool:
    pkg_key = str(pkg_name or "").strip().lower()
    if not pkg_key:
        return False
    current = installed_map if installed_map is not None else _current_installed(pyexe)
    if pkg_key not in current:
        if pkg_key in {"onnxruntime", "onnxruntime-gpu"}:
            return _cleanup_orphan_onnxruntime_namespace(
                pyexe,
                installed_map=current,
                log_fn=log_fn,
            ) > 0
        return False
    try:
        subprocess.run(
            [str(pyexe), "-m", "pip", "uninstall", pkg_key, "-y"],
            timeout=timeout,
            check=False,
            creationflags=flags
        )
        current.pop(pkg_key, None)
        if pkg_key in {"onnxruntime", "onnxruntime-gpu"}:
            _cleanup_orphan_onnxruntime_namespace(
                pyexe,
                installed_map=current,
                log_fn=log_fn,
            )
        if log_fn:
            log_fn(f"[OK] 已卸载冲突的 {pkg_key} ✅")
        return True
    except Exception as e:
        if log_fn:
            log_fn(f"[WARN] 卸载 {pkg_key} 失败（继续后续修复）: {e}")
        return False


def _repair_gpu_onnxruntime_runtime(pyexe: str, ort_gpu_spec: str, stop_event, pause_event, log_q,
                                    use_mirror: bool = False, force_reinstall: bool = False,
                                    no_cache: bool = False, proc_setter=None) -> tuple[bool, str]:
    installed_now = _current_installed(pyexe)
    if "onnxruntime" in installed_now:
        log_q.put("[INFO] 检测到 onnxruntime（CPU）被后续依赖重新带入，正在移除以避免覆盖 GPU providers...")
        log_q.put("[INFO] 注意：onnxruntime 和 onnxruntime-gpu 不能同时存在！")
        _uninstall_package_if_present(
            pyexe,
            "onnxruntime",
            installed_map=installed_now,
            log_fn=log_q.put,
        )

    ort_ok, ort_err = _verify_onnxruntime_runtime(pyexe, expect_gpu=True, timeout=45)
    if ort_ok:
        return True, ""

    log_q.put(f"[WARN] onnxruntime-gpu 运行时异常，先修复 ONNX 关键依赖链: {ort_err}")
    _fix_critical_versions(pyexe, log_q.put, use_mirror=use_mirror)

    ort_ok_after_deps, ort_err_after_deps = _verify_onnxruntime_runtime(
        pyexe, expect_gpu=True, timeout=45
    )
    if ort_ok_after_deps:
        return True, ""

    log_q.put(f"[WARN] ONNX 关键依赖修复后仍异常，刷新 onnxruntime-gpu 本体: {ort_err_after_deps}")
    repaired = _pip_install(
        pyexe,
        ort_gpu_spec,
        stop_event,
        log_q,
        use_mirror=use_mirror,
        flags=flags,
        pause_event=pause_event,
        force_reinstall=False,
        no_cache=no_cache,
        proc_setter=proc_setter,
    )
    if not repaired:
        return False, ort_err_after_deps or ort_err

    ort_ok2, ort_err2 = _verify_onnxruntime_runtime(pyexe, expect_gpu=True, timeout=45)
    return ort_ok2, (ort_err2 or ort_err_after_deps or ort_err)



LAYER_MAP = {
    "BASIC": [
        "lxml~=4.9.3",
        "pillow~=11.0.0", "pyperclip~=1.11.0",
        "requests~=2.32.5",
        "certifi~=2026.2.25",
        "psutil~=7.1.0",
    ],
    "CORE": [
        "transformers==4.55.4",
        "tokenizers==0.21.4",
        "sentencepiece==0.2.0",
        "opencv-python==4.13.0.92",
        "rapidocr==3.5.0",
        "numpy>=1.26,<3",
        "flatbuffers>=24.3.25",
        "coloredlogs>=15.0.1",
        "sympy>=1.13,<1.15",
        "protobuf>=3.20,<5",
        "latex2mathml>=3.81.0",
        "matplotlib~=3.10.8",
        "pymupdf~=1.27.2.2",
    ],
    "MATHCRAFT_CPU": [
        ORT_CPU_SPEC,
    ],
    "MATHCRAFT_GPU": [
        ORT_GPU_DEFAULT_SPEC,
    ],
    "PANDOC": [
        "pypandoc>=1.15",
    ],
}

MATHCRAFT_RUNTIME_LAYERS = ("MATHCRAFT_CPU", "MATHCRAFT_GPU")


def _sanitize_state_layers(state_path: Path, state: dict | None = None) -> dict:
    return _sanitize_state_layers_impl(
        state_path,
        valid_layers=set(LAYER_MAP),
        runtime_layers=MATHCRAFT_RUNTIME_LAYERS,
        state=state,
    )


def _normalize_chosen_layers(layers: list[str] | None) -> list[str]:
    return _normalize_chosen_layers_impl(layers, valid_layers=set(LAYER_MAP))

def _ensure_pip(main_python: Path) -> bool:
    """Ensure pip is available for the target interpreter."""
    import subprocess
    import urllib.request

    if not main_python.exists():
        raise RuntimeError(f"[ERR] 主 Python 不存在: {main_python}")

    # Verify this looks like a real python executable before bootstrap
    try:
        name = main_python.name.lower()
        is_python_exe = (
            (os.name == "nt" and name.startswith("python") and name.endswith(".exe"))
            or (os.name != "nt" and (name.startswith("python") or "python" in name))
        )
        if not is_python_exe:
            print(f"[WARN] pip bootstrap skipped for non-python executable: {main_python}")
            return False
    except Exception:
        pass



    try:
        pth_candidates = list(main_python.parent.glob("python*.pth")) + list(main_python.parent.glob("python*._pth"))
        for pth_file in pth_candidates:
            content = pth_file.read_text(encoding="utf-8")
            if "#import site" in content:
                from pathlib import Path
                Path(pth_file).write_text(content.replace("#import site", "import site"), encoding="utf-8")
    except Exception:
        pass


    def _pip_version_tuple(raw: str) -> tuple[int, ...]:
        parts: list[int] = []
        current = ""
        for ch in raw:
            if ch.isdigit():
                current += ch
            elif current:
                parts.append(int(current))
                current = ""
                if len(parts) >= 3:
                    break
        if current and len(parts) < 3:
            parts.append(int(current))
        return tuple(parts)

    def _query_pip_version() -> tuple[int, ...] | None:
        code = "import pip; print(pip.__version__)"
        proc = subprocess.run(
            [str(main_python), "-c", code],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=flags,
        )
        if proc.returncode != 0:
            return None
        return _pip_version_tuple(proc.stdout.strip())

    def _has_packaging_toolchain() -> bool:
        proc = subprocess.run(
            [str(main_python), "-c", "import setuptools, wheel"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
        return proc.returncode == 0

    def _upgrade_packaging_toolchain() -> bool:
        cmd = [
            str(main_python),
            "-m",
            "pip",
            "install",
            "--upgrade",
            "pip",
            "setuptools",
            "wheel",
            "--no-cache-dir",
            *PIP_INSTALL_SUPPRESS_ARGS,
        ]
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=flags,
        )
        if res.returncode != 0:
            print(f"[WARN] pip toolchain upgrade failed: {res.stdout[-1000:]}")
            return False
        return True

    pip_version = _query_pip_version()
    if pip_version is None:
        try:
            subprocess.check_call(
                [str(main_python), "-m", "ensurepip", "--upgrade"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=flags,
            )
            pip_version = _query_pip_version()
        except Exception:
            pip_version = None

    if pip_version is None:
        gp_url = "https://bootstrap.pypa.io/get-pip.py"
        gp_path = main_python.parent / "get-pip.py"
        urllib.request.urlretrieve(gp_url, gp_path)
        subprocess.check_call([str(main_python), str(gp_path)], timeout=180, creationflags=flags)
        pip_version = _query_pip_version()

    needs_upgrade = pip_version is None or pip_version < (23, 0) or not _has_packaging_toolchain()
    ok = True
    if needs_upgrade:
        ok = _upgrade_packaging_toolchain()
    if ok:
        pip_ready_event.set()
    return ok

def _current_installed(pyexe):
    """Return installed packages for the current environment."""
    def _installed_via_metadata() -> dict:
        """
        Fallback path when pip is unavailable/broken:
        query installed distributions via importlib.metadata.
        """
        code = (
            "import json\n"
            "try:\n"
            "  from importlib import metadata as _md\n"
            "except Exception:\n"
            "  import importlib_metadata as _md\n"
            "out = {}\n"
            "for d in _md.distributions():\n"
            "  try:\n"
            "    n = (d.metadata.get('Name') or '').strip().lower()\n"
            "  except Exception:\n"
            "    n = ''\n"
            "  if not n:\n"
            "    continue\n"
            "  try:\n"
            "    v = (d.version or '').strip()\n"
            "  except Exception:\n"
            "    v = ''\n"
            "  out[n] = v\n"
            "print(json.dumps(out, ensure_ascii=False))\n"
        )
        try:
            with subprocess_lock:
                out = subprocess.check_output(
                    [str(pyexe), "-c", code],
                    text=True,
                    creationflags=flags,
                )
            payload = (out or "").strip()
            if not payload:
                return {}
            data = json.loads(payload)
            if isinstance(data, dict):
                print(f"[DEBUG] 已安装包数量(元数据回退): {len(data)}")
                return {str(k).lower(): str(v) for k, v in data.items()}
        except Exception as e:
            print(f"[WARN] importlib.metadata 回退失败: {e}")
        return {}

    try:
        with subprocess_lock:
            subprocess.check_call([str(pyexe), "-m", "pip", "--version"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    except Exception as e:
        print(f"[WARN] pip 不可用，使用元数据回退: {e}")
        return _installed_via_metadata()
    try:
        with subprocess_lock:
            out = subprocess.check_output(
                [str(pyexe), "-m", "pip", "list", "--disable-pip-version-check", "--format=json"],
                text=True, creationflags=flags)
        raw = (out or "").strip()
        data = None
        try:
            data = json.loads(raw)
        except Exception:
            # Robust parse for rare noisy stdout cases.
            left_idx = raw.find("[")
            right_idx = raw.rfind("]")
            if left_idx != -1 and right_idx != -1 and right_idx >= left_idx:
                data = json.loads(raw[left_idx:right_idx + 1])
            else:
                raise
        result = {d["name"].lower(): d["version"] for d in data}
        if not result:
            print("[WARN] pip list 返回 0 个包，使用元数据回退二次确认。")
            metadata_installed = _installed_via_metadata()
            if metadata_installed:
                return metadata_installed
        print(f"[DEBUG] 已安装包数量: {len(result)}")
        return result
    except Exception as e:
        print(f"[WARN] 获取已安装包列表失败，使用元数据回退: {e}")
        return _installed_via_metadata()

def _split_spec_name(spec: str) -> tuple[str, str]:
    """Return (package_name_lower, constraint_part)."""
    m = re.match(r"\s*([A-Za-z0-9_.\-]+)\s*(.*)$", spec or "")
    if not m:
        return "", ""
    return m.group(1).lower(), (m.group(2) or "").strip()

def _version_satisfies_spec(pkg_name: str, installed_ver: str, spec: str) -> bool:
    """Check whether installed version satisfies requirement spec."""
    name, constraint = _split_spec_name(spec)
    if not name:
        return True
    if not constraint:
        return True
    if pkg_name and name != pkg_name.lower():
        return True
    try:
        from packaging.specifiers import SpecifierSet
        from packaging.version import Version
        return Version(installed_ver or "") in SpecifierSet(constraint)
    except Exception:
        return True

def _filter_packages(pkgs):
    res = []
    seen = set()
    for spec in pkgs:
        name = re.split(r'[<>=!~ ]', spec, 1)[0].strip().lower()
        if name in seen:
            continue
        seen.add(name)
        res.append(spec)
    return _reorder_mathcraft_install_specs(res)


def _reorder_mathcraft_install_specs(pkgs, gpu_runtime_first=False):
    """Keep MathCraft / ONNX dependency chain in a stable order to reduce pip backtracking."""
    if not pkgs:
        return []
    names = {
        re.split(r'[<>=!~ ]', spec, 1)[0].strip().lower()
        for spec in pkgs
    }
    if gpu_runtime_first or "onnxruntime-gpu" in names:
        priority = (
            "onnxruntime-gpu",
            "transformers",
            "tokenizers",
            "rapidocr",
            "opencv-python",
            "pymupdf",
        )
    else:
        priority = (
            "onnxruntime",
            "transformers",
            "tokenizers",
            "rapidocr",
            "opencv-python",
            "pymupdf",
        )
    grouped = {k: [] for k in priority}
    tail = []
    for spec in pkgs:
        name = re.split(r'[<>=!~ ]', spec, 1)[0].strip().lower()
        if name in grouped:
            grouped[name].append(spec)
        else:
            tail.append(spec)
    out = []
    for k in priority:
        out.extend(grouped[k])
    out.extend(tail)
    return out


def _gpu_available():
    try:
        r = subprocess.run(["nvidia-smi"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", timeout=2, creationflags=flags)
        return r.returncode == 0
    except Exception:
        return False


def _cuda_toolkit_available():
    try:
        r = subprocess.run(
            ["nvcc", "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=2,
            creationflags=flags,
        )
    except Exception:
        return False
    output = f"{r.stdout or ''}\n{r.stderr or ''}".lower()
    return r.returncode == 0 and "cuda" in output


def _diagnose_install_failure(output: str, returncode: int) -> str:
    """Diagnose common package installation failures."""
    output_lower = output.lower()

    if ("antlr4-python3-runtime" in output_lower) and ("bdist_wheel" in output_lower):
        return "🧩 antlr4-python3-runtime 构建环境缺少 wheel - 可先补齐 pip/setuptools/wheel 并关闭 build isolation"


    if any(x in output_lower for x in [
        "permission denied",
        "access is denied",
        "being used by another process",
        "permissionerror",
        "winerror 5",
        "winerror 32",
        "errno 13",
    ]):
        return "🔒 文件被占用或权限不足 - 请关闭程序后重试，或以管理员身份运行"


    if any(x in output_lower for x in [
        "conflicting dependencies",
        "incompatible",
        "no matching distribution",
        "could not find a version",
        "resolutionimpossible",
        "package requires",
    ]):
        return "⚠️ 依赖版本冲突 - 某些包的版本要求互相矛盾"


    if any(x in output_lower for x in [
        "connection refused",
        "connection timed out",
        "could not fetch url",
        "network is unreachable",
        "name or service not known",
        "getaddrinfo failed",
        "ssl: certificate",
        "readtimeouterror",
        "connectionerror",
    ]):
        return "🌐 网络连接失败 - 请检查网络或尝试使用镜像源"


    if any(x in output_lower for x in [
        "no space left",
        "disk full",
        "not enough space",
        "oserror: [errno 28]",
    ]):
        return "💾 磁盘空间不足 - 请清理磁盘后重试"


    if any(x in output_lower for x in [
        "building wheel",
        "failed building",
        "error: command",
        "microsoft visual c++",
        "vcvarsall.bat",
        "cl.exe",
    ]):
        return "🔧 编译失败 - 可能缺少 Visual C++ Build Tools"


    if any(x in output_lower for x in [
        "requires python",
        "python_requires",
        "not supported",
    ]):
        return "🐍 Python 版本不兼容 - 该包不支持当前 Python 版本"


    if any(x in output_lower for x in [
        "pip._internal",
        "attributeerror",
        "modulenotfounderror: no module named 'pip'",
    ]):
        return "📦 pip 损坏或版本过低 - 请先升级 pip"


    if any(x in output_lower for x in [
        "cuda",
        "cudnn",
        "nvidia",
        "gpu",
    ]) and "error" in output_lower:
        return "🎮 CUDA/GPU 相关错误 - 请检查 CUDA 版本是否匹配"


    if returncode == 1:
        return f"❓ 一般错误 (code={returncode}) - 请查看上方日志获取详情"
    elif returncode == 2:
        return f"❓ 命令行语法错误 (code={returncode})"
    else:
        return f"❓ 未知错误 (code={returncode}) - 请查看上方日志获取详情"



def _pip_install(pyexe, pkg, stop_event, log_q, use_mirror=False, flags=0, pause_event=None,
                 force_reinstall=False, no_cache=False, proc_setter=None):
    """Install one dependency package with live logs, mirrors, retries, and nonblocking output."""
    return PipInstallRunner(
        pyexe=pyexe,
        pkg=pkg,
        stop_event=stop_event,
        log_q=log_q,
        use_mirror=use_mirror,
        flags=flags,
        pause_event=pause_event,
        force_reinstall=force_reinstall,
        no_cache=no_cache,
        proc_setter=proc_setter,
        pip_ready_event=pip_ready_event,
        suppress_args=PIP_INSTALL_SUPPRESS_ARGS,
        safe_run=safe_run,
        subprocess_lock=subprocess_lock,
        onnxruntime_gpu_policy=onnxruntime_gpu_policy,
        cleanup_orphan_onnxruntime_namespace=_cleanup_orphan_onnxruntime_namespace,
        diagnose_install_failure=_diagnose_install_failure,
    ).install()

# --------------- UI ---------------
def _build_layers_ui(pyexe, deps_dir, installed_layers, default_select, chosen, state_path,
                     from_settings=False, skip_runtime_verify_once=False):

    from PyQt6.QtGui import QColor, QPalette
    from PyQt6.QtCore import QSize
    from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QCheckBox, QLabel,
                                 QHBoxLayout, QLineEdit, QMessageBox, QApplication, QToolButton)
    from qfluentwidgets import PushButton, FluentIcon, ComboBox

    def _is_dark_ui() -> bool:
        app = QApplication.instance()
        if app is None:
            return False
        c = app.palette().window().color()
        return ((c.red() + c.green() + c.blue()) / 3.0) < 128


    _sync_deps_fluent_theme()

    theme = {
        "dialog_bg": "#1b1f27" if _is_dark_ui() else "#ffffff",
        "text": "#e7ebf0" if _is_dark_ui() else "#222222",
        "muted": "#a9b3bf" if _is_dark_ui() else "#555555",
        "input_bg": "#232934" if _is_dark_ui() else "#ffffff",
        "border": "#465162" if _is_dark_ui() else "#d0d7de",
        "warn": "#ff8a80" if _is_dark_ui() else "#c62828",
        "ok": "#7bd88f" if _is_dark_ui() else "#2e7d32",
        "hint": "#d9b36c" if _is_dark_ui() else "#856404",
        "accent": "#8ec5ff" if _is_dark_ui() else "#1976d2",
        "accent_hover": "#63b3ff" if _is_dark_ui() else "#0f62c9",
        "btn_bg": "#2b3440" if _is_dark_ui() else "#f8fbff",
        "btn_hover": "#344151" if _is_dark_ui() else "#eef6ff",
    }

    def _style_layer_checkbox(cb, warn_text=False):
        text_color = theme["warn"] if warn_text else (theme["text"] if cb.isEnabled() else theme["muted"])
        disabled_color = theme["muted"]
        pal = cb.palette()
        for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
            pal.setColor(group, QPalette.ColorRole.WindowText, QColor(text_color))
            pal.setColor(group, QPalette.ColorRole.ButtonText, QColor(text_color))
            pal.setColor(group, QPalette.ColorRole.Text, QColor(text_color))
        pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(disabled_color))
        pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(disabled_color))
        pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(disabled_color))
        cb.setPalette(pal)
        cb.setStyleSheet(
            f"QCheckBox {{ color: {text_color}; spacing: 3px; padding-left: 3px; }}"
            f"QCheckBox:disabled {{ color: {disabled_color}; }}"
        )
        cb.style().unpolish(cb)
        cb.style().polish(cb)
        cb.update()

    def _style_installed_layer_label(cb):
        _style_layer_checkbox(cb)
        fill = "#3a4350" if _is_dark_ui() else "#d8dee6"
        border = "#556170" if _is_dark_ui() else "#c0c7d0"
        cb.setStyleSheet(
            f"QCheckBox {{ color: {theme['muted']}; spacing: 3px; padding-left: 3px; }}"
            "QCheckBox:disabled { color: " + theme["muted"] + "; }"
            "QCheckBox::indicator {"
            " width: 14px;"
            " height: 14px;"
            " margin: 0px;"
            " padding: 0px;"
            f" border: 1px solid {border};"
            " border-radius: 4px;"
            f" background: {fill};"
            " image: none;"
            "}"
            "QCheckBox::indicator:disabled,"
            "QCheckBox::indicator:unchecked:disabled,"
            "QCheckBox::indicator:checked:disabled {"
            f" border: 1px solid {border};"
            " border-radius: 4px;"
            f" background: {fill};"
            " image: none;"
            "}"
        )
        cb.style().unpolish(cb)
        cb.style().polish(cb)
        cb.update()

    def _style_layer_delete_button(btn):
        btn.setFixedSize(30, 30)
        btn.setIcon(FluentIcon.DELETE.icon())
        btn.setIconSize(QSize(18, 18))
        btn.setToolTip("删除该依赖层")
        btn.setStyleSheet(f"""
            QToolButton {{
                background: transparent;
                border: 1px solid transparent;
                border-radius: 4px;
                color: {theme['muted']};
                padding: 0px;
                margin: 0px;
            }}
            QToolButton:hover {{
                background: {theme['btn_hover']};
                color: {theme['warn']};
                border: 1px solid {theme['warn']};
            }}
            QToolButton:pressed {{
                background: {theme['input_bg']};
                color: {theme['warn']};
                border: 1px solid {theme['warn']};
            }}
        """)

    dlg = QDialog()
    icon_path = resource_path("assets/icon.ico")
    if os.path.exists(icon_path):
        dlg.setWindowIcon(QIcon(icon_path))
    dlg.setWindowTitle("依赖管理向导")
    lay = QVBoxLayout(dlg)
    lay.setSpacing(8)
    lay.setContentsMargins(16, 16, 16, 12)

    def _force_quit():

        try:
            global stop_event
            if 'stop_event' in globals():
                stop_event.set()
        except Exception:
            pass

        QTimer.singleShot(0, lambda: QApplication.instance().quit())
        QTimer.singleShot(20, lambda: sys.exit(0))

    def _on_close(evt):
        evt.accept()
        _force_quit()


    state_path = Path(state_path)
    state_file = str(state_path)
    claimed_layers = []
    failed_layer_names = []
    if os.path.exists(state_file):
        try:
            state = _load_json(Path(state_file), {"installed_layers": []})
            state = _sanitize_state_layers(Path(state_file), state)
            claimed_layers = state.get("installed_layers", [])
            failed_layer_names = state.get("failed_layers", [])
        except Exception:
            pass




    failed_layers = []
    verified_layers = []
    verified_in_ui = False
    skip_verify = bool(skip_runtime_verify_once) or (
        not from_settings and "BASIC" in claimed_layers and "CORE" in claimed_layers
    )
    if skip_verify:
        installed_layers["layers"] = claimed_layers
        verified_in_ui = bool(skip_runtime_verify_once)
    else:
        verified_layers = []
        failed_layers = []
        if claimed_layers and pyexe and os.path.exists(pyexe):
            verified_in_ui = True
            print("[INFO] 正在验证已安装的功能层...")
            for layer in claimed_layers:
                ok, err = _verify_layer_runtime(pyexe, layer, timeout=30)
                if ok:
                    verified_layers.append(layer)
                    print(f"  [OK] {layer} 验证通过")
                else:
                    failed_layers.append((layer, err))
                    print(f"  [FAIL] {layer} 验证失败: {err[:100]}")
            installed_layers["layers"] = verified_layers
            if failed_layers:
                failed_layer_names = [layer for layer, _ in failed_layers]
            try:
                payload = {"installed_layers": verified_layers}
                if failed_layers:
                    payload["failed_layers"] = [layer for layer, _ in failed_layers]
                _save_json(state_file, payload)
                if failed_layers:
                    print(f"[INFO] 已更新状态文件，移除失败的层: {[layer for layer, _ in failed_layers]}")
            except Exception as e:
                print(f"[WARN] 更新状态文件失败: {e}")
        else:
            installed_layers["layers"] = claimed_layers


    py_ready = bool(pyexe and os.path.exists(str(pyexe)))


    missing_layers = []
    if "BASIC" not in installed_layers["layers"]:
        missing_layers.append("BASIC")
    if "CORE" not in installed_layers["layers"]:
        missing_layers.append("CORE")
    if not any(layer in installed_layers["layers"] for layer in MATHCRAFT_RUNTIME_LAYERS):
        missing_layers.append("MATHCRAFT_CPU")

    def _build_status_text(current_deps_dir: str, current_py_ready: bool,
                           current_installed_layers: list[str], current_failed_layers: list[str]) -> tuple[str, str]:
        if not current_py_ready:
            return (
                f"当前依赖环境： {current_deps_dir}\n"
                "⚠️ 该目录尚未检测到可复用的 Python 环境。\n"
                "如需在此目录安装依赖，请先点击【下载】并按提示初始化。",
                theme["hint"],
            )
        if current_failed_layers:
            return (
                f"当前依赖环境： {current_deps_dir}\n"
                f"⚠️ 以下功能层安装但无法使用: {', '.join(current_failed_layers)}\n"
                f"可用功能层： {', '.join(current_installed_layers) if current_installed_layers else '(无)'}",
                theme["warn"],
            )
        if current_installed_layers:
            if any(required_layer not in current_installed_layers for required_layer in ("BASIC", "CORE")) or not any(layer in current_installed_layers for layer in MATHCRAFT_RUNTIME_LAYERS):
                return (
                    f"检测到当前环境 {current_deps_dir} 的功能层不完整\n"
                    f"已完整安装的功能层：{', '.join(current_installed_layers)}",
                    theme["muted"],
                )
            return (
                f"当前依赖环境： {current_deps_dir}\n"
                f"已完整安装的功能层：{', '.join(current_installed_layers)}",
                theme["ok"],
            )
        return (
            f"当前依赖环境： {current_deps_dir}\n已安装层：(无)",
            theme["warn"],
        )

    status_text, status_color = _build_status_text(
        deps_dir,
        py_ready,
        installed_layers["layers"],
        failed_layer_names,
    )

    env_info = QLabel(status_text)
    env_info.setStyleSheet(f"color:{status_color};font-size:12px;margin-bottom:4px;")
    lay.addWidget(env_info)
    lay.addWidget(QLabel("选择需要安装的功能层:"))


    failed_layer_names = list(dict.fromkeys(failed_layer_names))

    checks = {}
    delete_buttons = {}

    def _effective_default_select() -> set[str]:
        defaults = {"BASIC", "CORE"}
        active_runtime = {
            str(x) for x in (installed_layers.get("layers", []) or [])
            if str(x) in MATHCRAFT_RUNTIME_LAYERS
        }
        active_runtime.update(
            str(x) for x in (failed_layer_names or [])
            if str(x) in MATHCRAFT_RUNTIME_LAYERS
        )
        if not active_runtime:
            defaults.add("MATHCRAFT_CPU")
        return defaults

    def _sync_layer_checkbox(layer: str, cb, del_btn, effective_defaults: set[str]) -> None:
        if layer in failed_layer_names:
            cb.setChecked(True)
            cb.setEnabled(True)
            cb.setText(f"{layer}（需要修复）")
            _style_layer_checkbox(cb, warn_text=True)
            del_btn.setVisible(True)
            del_btn.setEnabled(True)
        elif layer in installed_layers["layers"]:
            cb.setChecked(False)
            cb.setEnabled(False)
            cb.setText(f"{layer}（已安装）")
            _style_installed_layer_label(cb)
            del_btn.setVisible(True)
            del_btn.setEnabled(True)
        else:
            cb.setEnabled(True)
            cb.setChecked(layer in effective_defaults)
            cb.setText(layer)
            _style_layer_checkbox(cb)
            del_btn.setVisible(False)
            del_btn.setEnabled(False)

    def make_del_func(layer_name):
        def _del():
            reply = _exec_close_only_message_box(
                dlg,
                "删除确认",
                f"确定要删除层 [{layer_name}] 及其所有依赖包吗？\n\n确认后将打开卸载进度窗口，并在当前程序内执行卸载。",
                icon=QMessageBox.Icon.Warning,
                buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                default_button=QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                pkgs = list(LAYER_MAP.get(layer_name, []))
                pkg_names = []
                for pkg in pkgs:
                    pkg_name = pkg.split('~')[0].split('=')[0].split('>')[0].split('<')[0].strip()
                    if pkg_name and pkg_name not in pkg_names:
                        pkg_names.append(pkg_name)
                pdlg, info2, logw2, btn_cancel2, btn_pause2, progress2 = _progress_dialog()
                pdlg.setWindowTitle("卸载进度")
                info2.setText(f"正在卸载层 {layer_name}，请不要关闭此窗口...")
                btn_pause2.hide()
                btn_cancel2.setText("关闭")
                btn_cancel2.setEnabled(False)

                worker = UninstallLayerWorker(str(pyexe), state_file, layer_name, pkg_names)
                worker.log_updated.connect(logw2.append)
                worker.progress_updated.connect(progress2.setValue)

                def _on_done(success: bool, removed_layer: str):
                    btn_cancel2.setEnabled(True)
                    btn_cancel2.setText("完成")
                    try:
                        btn_cancel2.clicked.disconnect()
                    except Exception:
                        pass
                    btn_cancel2.clicked.connect(lambda: pdlg.accept())
                    if success:
                        info2.setText(f"层 {removed_layer} 已卸载完成。点击完成返回依赖向导。")
                        try:
                            if removed_layer in installed_layers["layers"]:
                                installed_layers["layers"].remove(removed_layer)
                        except Exception:
                            pass
                        try:
                            dlg.refresh_ui()
                        except Exception:
                            pass
                    else:
                        info2.setText(f"层 {removed_layer} 卸载过程中存在问题，请查看日志。")
                    progress2.setValue(100)

                worker.done.connect(_on_done)
                worker.start()
                pdlg.exec()
        return _del


    effective_default_select = _effective_default_select()
    for layer in LAYER_MAP.keys():
        row = QHBoxLayout()
        cb = QCheckBox(layer)
        del_btn = QToolButton()
        _style_layer_delete_button(del_btn)
        del_btn.clicked.connect(make_del_func(layer))
        _sync_layer_checkbox(layer, cb, del_btn, effective_default_select)
        checks[layer] = cb
        delete_buttons[layer] = del_btn
        row.addWidget(cb)
        row.addWidget(del_btn)
        lay.addLayout(row)


    def on_mathcraft_cpu_changed(state):
        if state and checks.get("MATHCRAFT_GPU") and checks["MATHCRAFT_GPU"].isEnabled():
            checks["MATHCRAFT_GPU"].setChecked(False)

    def on_mathcraft_gpu_changed(state):
        if state and checks.get("MATHCRAFT_CPU") and checks["MATHCRAFT_CPU"].isEnabled():
            checks["MATHCRAFT_CPU"].setChecked(False)

    if "MATHCRAFT_CPU" in checks:
        checks["MATHCRAFT_CPU"].stateChanged.connect(on_mathcraft_cpu_changed)
    if "MATHCRAFT_GPU" in checks:
        checks["MATHCRAFT_GPU"].stateChanged.connect(on_mathcraft_gpu_changed)


    gpu_info_label = QLabel()

    def _refresh_gpu_info_label() -> None:
        current_installed_layers = {
            str(layer) for layer in (installed_layers.get("layers", []) or [])
        }
        current_failed_layers = {str(layer) for layer in (failed_layer_names or [])}
        if "MATHCRAFT_GPU" in current_installed_layers:
            text = "✅ MATHCRAFT_GPU 已安装，GPU 加速可用"
            color = theme["ok"]
        elif "MATHCRAFT_GPU" in current_failed_layers:
            text = "⚠️ MATHCRAFT_GPU 验证失败，请使用MATHCRAFT_CPU后端"
            color = theme["warn"]
        elif _gpu_available() and _cuda_toolkit_available():
            text = "✅ 检测到 NVIDIA GPU 和 CUDA Toolkit；可尝试 MATHCRAFT_GPU"
            color = theme["ok"]
        elif _gpu_available():
            text = "⚠️ 未检测到 nvcc/CUDA Toolkit，建议使用 MATHCRAFT_CPU后端"
            color = theme["hint"]
        else:
            text = "⚠️ 未检测到 NVIDIA GPU，建议使用默认 MATHCRAFT_CPU 后端"
            color = theme["hint"]
        gpu_info_label.setText(text)
        gpu_info_label.setStyleSheet(f"color:{color};font-size:12px;margin:4px 0;")

    _refresh_gpu_info_label()
    lay.addWidget(gpu_info_label)

    path_row = QHBoxLayout()
    path_edit = QLineEdit(deps_dir)
    path_edit.setReadOnly(True)
    btn_path = PushButton(FluentIcon.FOLDER, "更改依赖安装/加载路径")
    btn_path.setFixedHeight(36)
    btn_path.setToolTip("更改后会立即刷新当前依赖环境状态")
    path_row.addWidget(QLabel("依赖安装/加载路径:"))
    path_row.addWidget(path_edit, 1)
    path_row.addWidget(btn_path)
    lay.addLayout(path_row)


    mirror_row = QHBoxLayout()
    mirror_row.setContentsMargins(0, 0, 0, 0)
    mirror_row.setSpacing(6)
    mirror_row.addWidget(QLabel("下载源:"))
    mirror_box = ComboBox()
    mirror_box.addItem("官方 PyPI", userData="off")
    mirror_box.addItem("清华镜像", userData="tuna")
    mirror_box.setFixedHeight(30)
    mirror_row.addWidget(mirror_box, 1)
    lay.addLayout(mirror_row)

    def _current_mirror_source() -> str:
        try:
            idx = int(mirror_box.currentIndex())
        except Exception:
            idx = -1
        value = None
        if idx >= 0:
            try:
                value = mirror_box.itemData(idx)
            except Exception:
                value = None
        if value is None:
            try:
                text = str(mirror_box.currentText()).strip()
            except Exception:
                text = ""
            value = "tuna" if "清华" in text else "off"
        value = str(value or "off").strip().lower()
        return "tuna" if value == "tuna" else "off"

    def _load_saved_mirror_source() -> str:
        try:
            cfg_path = _load_config_path()
            if cfg_path.exists():
                data = json.loads(cfg_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    saved = str(data.get("deps_mirror_source", "")).strip().lower()
                    if saved in ("off", "tuna"):
                        return saved
        except Exception:
            pass
        return "off"

    def _save_mirror_source(source: str) -> None:
        try:
            cfg_path = _load_config_path()
            cfg = {}
            if cfg_path.exists():
                try:
                    cfg = json.loads(cfg_path.read_text(encoding="utf-8")) or {}
                except Exception:
                    cfg = {}
            cfg["deps_mirror_source"] = source
            cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    _saved_mirror = _load_saved_mirror_source()
    mirror_box.setCurrentIndex(1 if _saved_mirror == "tuna" else 0)

    def _on_mirror_changed(_index: int) -> None:
        _save_mirror_source(_current_mirror_source())

    mirror_box.currentIndexChanged.connect(_on_mirror_changed)


    btn_row = QHBoxLayout()

    btn_download = PushButton(FluentIcon.DOWNLOAD, "下载")
    btn_download.setFixedHeight(36)
    btn_enter = PushButton(FluentIcon.PLAY, "进入")
    btn_enter.setFixedHeight(36)
    btn_enter.setDefault(True)
    btn_cancel = PushButton(FluentIcon.CLOSE, "退出程序")
    btn_cancel.setFixedHeight(36)
    btn_row.addWidget(btn_download)
    btn_row.addWidget(btn_enter)
    btn_row.addWidget(btn_cancel)
    lay.addLayout(btn_row)


    warn = QLabel("缺少关键依赖层，部分功能将不可用！")
    warn.setStyleSheet(f"color:{theme['warn']};")
    lay.addWidget(warn)


    desc = QLabel(
        "📦 层级说明：\n"
        "• BASIC：基础运行层，包含网络、图像处理和通用工具依赖。\n"
        "• CORE：识别功能层，包含 MathCraft ONNX OCR 及文档导出 / PDF 相关依赖。\n"
        "• MATHCRAFT_CPU：ONNX Runtime CPU 后端，默认推荐，稳定性更高。\n"
        "• MATHCRAFT_GPU：ONNX Runtime GPU 后端，需要本机 NVIDIA 驱动 / CUDA DLL 可用。\n"
        "• PANDOC：可选 Pandoc 导出后端，支持 docx/odt/epub/rtf 等文档格式转换。\n"
        "• 识别功能实际运行需要 BASIC + CORE + 一个 MathCraft 后端。\n"
        "• 默认推荐 BASIC + CORE + MATHCRAFT_CPU；如需 GPU 推理请手动勾选 MATHCRAFT_GPU。\n"
        "\n"
        "⚠️ 重要提示：\n"
        "• MATHCRAFT_CPU 和 MATHCRAFT_GPU 互斥；切换时会自动清理冲突的 onnxruntime 组件。\n"
        "• 已安装层会在进入向导时重新验证；验证失败的层会标记为“需要修复”。\n"
        "• 本向导只管理内置 MathCraft 依赖链，不管理外部模型服务本身。\n"
        "• 若你只使用外部模型，可点击“跳过安装并进入”通过设置页面进行配置。"
    )
    desc.setStyleSheet(f"color:{theme['muted']};font-size:11px;line-height:1.35;")
    lay.addWidget(desc)

    chosen = {
        "layers": None,
        "mirror": False,
        "mirror_source": _current_mirror_source(),
        "deps_path": deps_dir,
        "force_enter": False,
        "verified_in_ui": verified_in_ui,
        "action": None,
    }

    def _current_deps_dir() -> str:
        try:
            text = path_edit.text().strip()
            return text or deps_dir
        except Exception:
            return deps_dir

    def _current_py_ready() -> bool:
        try:
            return bool(_find_existing_python(Path(_current_deps_dir())))
        except Exception:
            return False


    def update_ui():
        required = {"BASIC", "CORE"}
        missing = [required_layer for required_layer in required if required_layer not in installed_layers["layers"]]
        if not any(layer in installed_layers["layers"] for layer in MATHCRAFT_RUNTIME_LAYERS):
            missing.append("MATHCRAFT_CPU")
        is_lack_critical = bool(missing)
        py_ready = _current_py_ready()
        if not py_ready:
            btn_enter.setText("不可进入(先初始化)")
            btn_enter.setEnabled(False)
            warn.setVisible(True)
            return
        btn_enter.setEnabled(True)
        btn_enter.setText("跳过安装并进入" if is_lack_critical else "进入")
        warn.setVisible(is_lack_critical)

    update_ui()

    def choose_path():
        nonlocal failed_layer_names, state_file, state_path, pyexe
        import os
        d = _select_existing_directory_with_icon(dlg, "选择依赖安装/加载目录", deps_dir)
        if d:
            normalized = str(_normalize_deps_base_dir(Path(d)))
            path_edit.setText(normalized)
            normalized_path = Path(normalized)
            _default_pyexe_name = "python.exe" if os.name == "nt" else "python3"
            active_pyexe = _find_existing_python(normalized_path) or (normalized_path / "python311" / _default_pyexe_name)
            pyexe = active_pyexe
            state_path = normalized_path / STATE_FILE
            state_file = str(state_path)
            chosen["deps_path"] = normalized
            chosen["verified_in_ui"] = False
            installed_layers["layers"] = []
            failed_layer_names = []
            if os.path.exists(state_file):
                try:
                    state = _load_json(Path(state_file), {"installed_layers": []})
                    state = _sanitize_state_layers(Path(state_file), state)
                    installed_layers["layers"] = state.get("installed_layers", [])
                    failed_layer_names = state.get("failed_layers", [])
                except Exception:
                    pass
            py_ready_local = bool(active_pyexe and Path(active_pyexe).exists())
            status_text, status_color = _build_status_text(
                normalized,
                py_ready_local,
                installed_layers["layers"],
                failed_layer_names,
            )
            env_info.setText(status_text)
            env_info.setStyleSheet(f"color:{status_color};font-size:12px;margin-bottom:4px;")
            effective_default_select = _effective_default_select()
            for layer, cb in checks.items():
                _sync_layer_checkbox(layer, cb, delete_buttons[layer], effective_default_select)
            _refresh_gpu_info_label()

            update_ui()

            config_path = str(_load_config_path())
            cfg = {}
            if os.path.exists(config_path):
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                except Exception:
                    pass
            cfg["install_base_dir"] = normalized
            try:
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
                os.environ["LATEXSNIPPER_INSTALL_BASE_DIR"] = normalized
                os.environ["LATEXSNIPPER_DEPS_DIR"] = normalized
                if active_pyexe and Path(active_pyexe).exists():
                    os.environ["LATEXSNIPPER_PYEXE"] = str(active_pyexe)
                print(f"[INFO] 依赖路径已保存并刷新状态: {normalized}")
            except Exception as e:
                print(f"[ERR] 保存配置失败: {e}")

    btn_path.clicked.connect(choose_path)

    def enter():
        """Enter when the environment is complete, or apply the configured skip policy."""
        sel = _normalize_chosen_layers([L for L, c in checks.items() if c.isChecked()])
        mirror_source = _current_mirror_source()
        chosen["layers"] = sel
        chosen["mirror"] = (mirror_source == "tuna")
        chosen["mirror_source"] = mirror_source
        chosen["deps_path"] = path_edit.text()
        _save_mirror_source(mirror_source)

        if not _current_py_ready():
            custom_warning_dialog(
                "不可进入",
                "当前依赖目录尚未检测到可复用的 Python 环境。\n请先点击“下载”初始化依赖环境后再进入主程序。",
                dlg
            )
            return

        print(f"[DEBUG] Selected layers: {sel}")
        required = {"BASIC", "CORE"}
        missing = [required_layer for required_layer in required if required_layer not in installed_layers["layers"]]
        if not any(layer in installed_layers["layers"] for layer in MATHCRAFT_RUNTIME_LAYERS):
            missing.append("MATHCRAFT_CPU")


        if not missing:
            chosen["action"] = "enter"
            chosen["layers"] = []
            chosen["force_enter"] = False
            dlg.accept()
            return


        chosen["action"] = "enter"
        chosen["layers"] = []
        chosen["force_enter"] = True
        dlg.done(1)

    btn_enter.clicked.connect(enter)

    def download():
        sel = _normalize_chosen_layers([L for L, c in checks.items() if c.isChecked()])
        if not sel:
            from qfluentwidgets import InfoBar, InfoBarPosition
            InfoBar.warning(
                title="提示",
                content="请至少选择一个依赖层进行下载。",
                parent=dlg.parent() if dlg.parent() is not None else dlg,
                duration=3000,
                position=InfoBarPosition.TOP,
            )
            return
        chosen["layers"] = sel
        mirror_source = _current_mirror_source()
        chosen["mirror"] = (mirror_source == "tuna")
        chosen["mirror_source"] = mirror_source
        chosen["deps_path"] = path_edit.text()
        chosen["force_enter"] = False
        chosen["action"] = "download"
        _save_mirror_source(mirror_source)
        dlg.accept()

    btn_download.clicked.connect(download)

    from PyQt6.QtCore import QTimer

    def _ask_exit_confirm() -> QMessageBox.StandardButton:
        return _exec_close_only_message_box(
            dlg,
            "退出确认",
            "确定要退出安装向导并关闭程序吗？",
            icon=QMessageBox.Icon.Question,
            buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            default_button=QMessageBox.StandardButton.No,
        )


    def refresh_ui():
        """Refresh dependency state after installation completes."""
        nonlocal failed_layer_names
        try:
            new_state = _sanitize_state_layers(Path(state_path))
            installed_layers["layers"] = new_state.get("installed_layers", [])
            failed_layer_names = new_state.get("failed_layers", [])


            if (
                "BASIC" in installed_layers["layers"]
                and "CORE" in installed_layers["layers"]
                and any(layer in installed_layers["layers"] for layer in MATHCRAFT_RUNTIME_LAYERS)
            ):
                warn.setVisible(False)
                btn_enter.setText("进入")
            else:
                warn.setVisible(True)
                btn_enter.setText("跳过安装并进入")


            effective_default_select = _effective_default_select()
            for layer, cb in checks.items():
                _sync_layer_checkbox(layer, cb, delete_buttons[layer], effective_default_select)
            _refresh_gpu_info_label()

            current_dir = _current_deps_dir()
            py_ready_local = bool(_find_existing_python(Path(current_dir)))
            status_text, status_color = _build_status_text(
                current_dir,
                py_ready_local,
                installed_layers["layers"],
                failed_layer_names,
            )
            env_info.setText(status_text)
            env_info.setStyleSheet(f"color:{status_color};font-size:12px;margin-bottom:4px;")
            print("[OK] 依赖状态刷新成功 ✅")
        except Exception as e:
            print(f"[WARN] UI 刷新失败: {e}")


    dlg.refresh_ui = refresh_ui


    _closing_dialog = {"active": False}

    def _exit_app():
        """Confirm and exit the application."""
        if _closing_dialog["active"]:
            return
        reply = _ask_exit_confirm()
        if reply == QMessageBox.StandardButton.Yes:
            _closing_dialog["active"] = True
            try:
                main_mod = sys.modules.get("__main__")
                release_lock = getattr(main_mod, "_release_single_instance_lock", None) if main_mod is not None else None
                if callable(release_lock):
                    release_lock()
            except Exception as e:
                print(f"[WARN] 退出前释放程序锁失败: {e}")
            try:
                dlg.done(QDialog.DialogCode.Rejected)
            except Exception:
                pass
            try:
                app = QApplication.instance()
                if app is not None:
                    app.exit(0)
            except Exception:
                pass
            os._exit(0)

    btn_cancel.clicked.connect(_exit_app)


    def _on_close(evt):
        if _closing_dialog["active"]:
            evt.accept()
            return
        _exit_app()
        evt.ignore()
    dlg.closeEvent = _on_close

    return dlg, chosen

def _progress_dialog():
    from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTextEdit, QProgressBar, QHBoxLayout, QApplication
    from PyQt6.QtCore import QEvent
    from qfluentwidgets import PushButton, FluentIcon
    _sync_deps_fluent_theme()
    def _is_dark_ui() -> bool:
        try:
            import qfluentwidgets as qfw
            fn = getattr(qfw, "isDarkTheme", None)
            if callable(fn):
                return bool(fn())
        except Exception:
            pass
        app = QApplication.instance()
        if app is None:
            return False
        c = app.palette().window().color()
        return ((c.red() + c.green() + c.blue()) / 3.0) < 128

    def _theme_tokens() -> dict:
        dark = _is_dark_ui()
        return {
            "dark": dark,
            "dialog_bg": "#1b1f27" if dark else "#ffffff",
            "panel_bg": "#232934" if dark else "#f7f9fc",
            "text": "#e7ebf0" if dark else "#222222",
            "muted": "#a9b3bf" if dark else "#666666",
            "border": "#465162" if dark else "#d0d7de",
            "progress_bg": "#232934" if dark else "#ffffff",
            "progress_border": "#465162" if dark else "#cfd6dd",
            "progress_chunk": "#4c9aff" if dark else "#1976d2",
        }

    dlg = QDialog()
    dlg.setWindowTitle("安装进度")
    dlg.resize(680, 440)
    icon_path = resource_path("assets/icon.ico")
    if os.path.exists(icon_path):
        dlg.setWindowIcon(QIcon(icon_path))
    lay = QVBoxLayout(dlg)
    info = QLabel("正在遍历寻找缺失的库，完成后将自动下载，请不要关闭此窗口(๑•̀ㅂ•́)و✧)...")
    logw = QTextEdit()
    logw.setReadOnly(True)
    progress = QProgressBar()
    progress.setRange(0, 100)
    progress.setFixedHeight(20)
    progress.setMinimumWidth(400)

    btn_cancel = PushButton(FluentIcon.CLOSE, "退出下载")
    btn_cancel.setFixedHeight(32)
    btn_pause = PushButton(FluentIcon.PAUSE, "暂停下载")
    btn_pause.setFixedHeight(32)
    btn_row = QHBoxLayout()
    btn_row.addWidget(btn_pause)
    btn_row.addWidget(btn_cancel)
    lay.addWidget(info)
    lay.addWidget(logw, 1)
    lay.addWidget(progress)
    lay.addLayout(btn_row)

    def _apply_theme_styles(force: bool = False):
        theme = _theme_tokens()
        if (not force) and getattr(dlg, "_theme_is_dark_cached", None) == theme["dark"]:
            return
        dlg._theme_is_dark_cached = theme["dark"]

        info.setStyleSheet(f"color: {theme['muted']};")
        progress.setStyleSheet("""
            QProgressBar {
                border: 1px solid __PROGRESS_BORDER__;
                border-radius: 6px;
                text-align: center;
                background-color: __PROGRESS_BG__;
                color: __TEXT__;
            }
            QProgressBar::chunk {
                background: __PROGRESS_CHUNK__;
                border-radius: 6px;
            }
        """.replace("__PROGRESS_BORDER__", theme["progress_border"])
           .replace("__PROGRESS_BG__", theme["progress_bg"])
           .replace("__TEXT__", theme["text"])
           .replace("__PROGRESS_CHUNK__", theme["progress_chunk"]))

    _apply_theme_styles(force=True)

    _orig_event = dlg.event
    def _event_with_theme_refresh(event):
        if event.type() in (
            QEvent.Type.StyleChange,
            QEvent.Type.PaletteChange,
            QEvent.Type.ApplicationPaletteChange,
        ):
            _apply_theme_styles()
        return _orig_event(event)
    dlg.event = _event_with_theme_refresh

    _orig_show_event = dlg.showEvent
    def _show_event_with_theme_refresh(event):
        _apply_theme_styles(force=True)
        _orig_show_event(event)
    dlg.showEvent = _show_event_with_theme_refresh

    return dlg, info, logw, btn_cancel, btn_pause, progress

def _apply_close_only_window_flags(win):
    from PyQt6.QtCore import Qt
    flags = (
        win.windowFlags()
        | Qt.WindowType.CustomizeWindowHint
        | Qt.WindowType.WindowTitleHint
        | Qt.WindowType.WindowCloseButtonHint
        | Qt.WindowType.WindowSystemMenuHint
    )
    flags = (
        flags
        & ~Qt.WindowType.WindowMinimizeButtonHint
        & ~Qt.WindowType.WindowMaximizeButtonHint
        & ~Qt.WindowType.WindowMinMaxButtonsHint
        & ~Qt.WindowType.WindowContextHelpButtonHint
    )
    win.setWindowFlags(flags)


def _deps_dialog_theme() -> dict:
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    dark = False
    try:
        if app is not None:
            c = app.palette().window().color()
            dark = ((c.red() + c.green() + c.blue()) / 3.0) < 128
    except Exception:
        dark = False
    return {
        "dialog_bg": "#1b1f27" if dark else "#ffffff",
        "text": "#e7ebf0" if dark else "#222222",
        "muted": "#a9b3bf" if dark else "#555555",
        "panel_bg": "#232934" if dark else "#f8fbff",
        "border": "#465162" if dark else "#d0d7de",
        "accent": "#8ec5ff" if dark else "#1976d2",
        "btn_hover": "#344151" if dark else "#eef6ff",
    }


def _sync_deps_fluent_theme() -> None:
    try:
        from qfluentwidgets import setTheme, Theme
        t = _deps_dialog_theme()
        setTheme(Theme.DARK if t["dialog_bg"] == "#1b1f27" else Theme.LIGHT)
    except Exception:
        pass


def _apply_app_window_icon(win) -> None:
    from core.window_icons import apply_app_window_icon
    apply_app_window_icon(win, resource_path("assets/icon.ico"))


def _select_existing_directory_with_icon(parent, title: str, initial_dir: str) -> str:
    from PyQt6.QtWidgets import QFileDialog
    from core.window_icons import schedule_native_dialog_icon

    dlg = QFileDialog(parent, title, initial_dir)
    dlg.setFileMode(QFileDialog.FileMode.Directory)
    dlg.setOption(QFileDialog.Option.ShowDirsOnly, True)
    _apply_app_window_icon(dlg)
    icon_timer = schedule_native_dialog_icon(title, resource_path("assets/icon.ico"))
    try:
        if dlg.exec() != QFileDialog.DialogCode.Accepted:
            return ""
    finally:
        if icon_timer is not None:
            icon_timer.stop()
    selected = dlg.selectedFiles()
    return selected[0] if selected else ""

def _exec_close_only_message_box(
    parent,
    title: str,
    text: str,
    icon,
    buttons,
    default_button=None,
):
    from PyQt6.QtWidgets import QMessageBox
    msg = QMessageBox(parent)
    _apply_app_window_icon(msg)
    msg.setWindowTitle(title)
    msg.setText(text)
    msg.setIcon(icon)
    msg.setStandardButtons(buttons)
    if default_button is not None:
        msg.setDefaultButton(default_button)
    _apply_close_only_window_flags(msg)
    return QMessageBox.StandardButton(msg.exec())

def custom_warning_dialog(title, message, parent=None):
    from PyQt6.QtWidgets import QMessageBox as _QMessageBox
    _sync_deps_fluent_theme()
    _exec_close_only_message_box(
        parent,
        title,
        message,
        icon=_QMessageBox.Icon.Warning,
        buttons=_QMessageBox.StandardButton.Ok,
        default_button=_QMessageBox.StandardButton.Ok,
    )
    return True

def clear_deps_state():
    """Clear the dependency state file."""
    import json
    import os
    from pathlib import Path

    try:

        home_config = _load_config_path()
        print(f"[DEBUG] 清理状态文件：{home_config}")

        if not home_config.exists():
            print("[WARN] 配置文件不存在，无需清理。")
            return

        with open(home_config, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        deps_dir = cfg.get("install_base_dir")

        if not deps_dir or not os.path.exists(deps_dir):
            print(f"[ERR] 无法找到依赖目录：{deps_dir}")
            return


        state_path = Path(deps_dir) / ".deps_state.json"
        if state_path.exists():
            state_path.unlink()
            print(f"[OK] 已删除状态文件：{state_path}")


        with open(state_path, "w", encoding="utf-8") as f:
            json.dump({"installed_layers": []}, f, ensure_ascii=False, indent=2)
        print(f"[OK] 已重新生成空状态文件：{state_path}")

    except Exception as e:
        print(f"[ERR] 清除依赖状态文件失败: {e}")

def _load_config_path():
    return _config_dir_path() / CONFIG_FILE

def _read_config_install_dir(cfg_path: Path) -> str | None:
    if cfg_path.exists():
        try:
            import json
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            v = data.get("install_base_dir")
            if isinstance(v, str) and v.strip():
                return v
        except Exception:
            pass
    return None
def _write_config_install_dir(cfg_path: Path, deps_dir: str) -> None:
    try:
        import json
        data = {}
        if cfg_path.exists():
            try:
                data = json.loads(cfg_path.read_text(encoding="utf-8")) or {}
            except Exception:
                data = {}
        data["install_base_dir"] = deps_dir
        Path(cfg_path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

def _find_local_python311_installer(deps_dir: Path) -> Path | None:
    return _find_local_python311_installer_impl(deps_dir, __file__)


def _system_python_install_hint(reason: str) -> str:
    """Return platform-specific instructions for creating the dependency venv."""
    lines = [
        reason,
        "",
        "Please install Python 3.10+ with venv and pip support, then retry.",
    ]
    if sys.platform == "darwin":
        lines.extend([
            "  Homebrew: brew install python",
            "  python.org: install the latest macOS Python 3 package",
            "  After installation, reopen LaTeXSnipper.",
        ])
    else:
        lines.extend([
            "  Debian/Ubuntu: sudo apt install python3 python3-venv",
            "  Fedora:         sudo dnf install python3",
            "  Arch:           sudo pacman -S python",
        ])
    return "\n".join(lines)


def _setup_python_venv_from_system(target_dir: Path, timeout: int = 300) -> bool:
    """Create a Python venv at target_dir using the system python3 interpreter.

    Only meaningful on Linux/macOS.  On Windows this always returns False.
    """
    import time

    if os.name == "nt":
        return False

    system_python = _find_system_python3()
    if system_python is None:
        print("[WARN] 未找到系统 Python 3，无法创建 venv")
        return False

    target_dir.mkdir(parents=True, exist_ok=True)
    print(f"[INFO] 使用系统 Python 创建 venv: {system_python} -> {target_dir}")
    try:
        commands = [
            [str(system_python), "-m", "venv", "--copies", str(target_dir)],
            [str(system_python), "-m", "venv", "--copies", "--without-pip", str(target_dir)],
        ]
        last_output = ""
        for cmd in commands:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            deadline = time.monotonic() + timeout
            while True:
                ret = proc.poll()
                if ret is not None:
                    break
                if time.monotonic() >= deadline:
                    raise subprocess.TimeoutExpired(cmd, timeout)
                time.sleep(0.2)
            if ret == 0:
                print(f"[OK] venv 创建成功: {target_dir}")
                return True
            last_output = proc.stdout.read() if proc.stdout else ""
        print(f"[WARN] venv 创建失败: {last_output[-500:]}")
        return False
    except subprocess.TimeoutExpired:
        print(f"[WARN] venv 创建超时（{timeout} 秒）")
        try:
            proc.kill()
        except Exception:
            pass
        return False
    except Exception as e:
        print(f"[WARN] venv 创建异常: {e}")
        return False


def _run_local_python311_installer(installer: Path, target_dir: Path, timeout: int = 900,
                                   before_launch=None) -> bool:
    """
    Launch the local Python installer and wait for it to finish.
    The installer UI is shown to the user; no network download is attempted here.

    Windows-only: the .exe installer only exists on Windows.
    """
    if os.name != "nt":
        return False
    import time

    target_dir.mkdir(parents=True, exist_ok=True)
    print(f"[INFO] 正在启动本地 Python 安装器: {installer}")
    print(f"[INFO] 期望安装目录: {target_dir}")
    try:
        if callable(before_launch):
            try:
                before_launch()
            except Exception as e:
                print(f"[WARN] installer pre-launch callback failed: {e}")
        try:
            from PyQt6.QtWidgets import QApplication as _QApplication
            app = _QApplication.instance()
        except Exception:
            app = None
        proc = subprocess.Popen([str(installer)])
        deadline = time.monotonic() + timeout
        ret = None
        while True:
            ret = proc.poll()
            if ret is not None:
                break
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired([str(installer)], timeout)
            if app is not None:
                try:
                    app.processEvents()
                except Exception:
                    pass
            time.sleep(0.2)
        print(f"[INFO] Python 安装器已退出（返回码: {ret}）")
        time.sleep(1)
    except subprocess.TimeoutExpired:
        print(f"[WARN] Python 安装器超时（{timeout} 秒）")
        try:
            proc.kill()
        except Exception:
            pass
        return False
    except Exception as e:
        print(f"[WARN] 启动本地 Python 安装器失败: {e}")
        return False
    _default_pyexe_name = "python.exe" if os.name == "nt" else "python3"
    return (target_dir / _default_pyexe_name).exists()


def ensure_deps(prompt_ui=True, require_layers=("BASIC", "CORE"), force_enter=False, always_show_ui=False,
                deps_dir=None, from_settings=False, before_show_ui=None,
                after_force_enter=None):
    global _LAST_ENSURE_DEPS_FORCE_ENTER
    _LAST_ENSURE_DEPS_FORCE_ENTER = False
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv[:1])

    def _notify_before_show_ui():
        if not callable(before_show_ui):
            return
        try:
            before_show_ui()
        except Exception as e:
            print(f"[WARN] before_show_ui callback failed: {e}")

    def _notify_after_force_enter():
        if not callable(after_force_enter):
            return
        try:
            after_force_enter()
            try:
                app.processEvents()
            except Exception:
                pass
        except Exception as e:
            print(f"[WARN] after_force_enter callback failed: {e}")

    current_pyexe = Path(sys.executable)
    current_site = _site_packages_root(current_pyexe)


    cfg_path = _load_config_path()
    if not deps_dir:
        deps_dir = _read_config_install_dir(cfg_path)

    if not deps_dir:
        parent = app.activeWindow()
        _notify_before_show_ui()
        chosen = _select_existing_directory_with_icon(parent, "选择依赖安装/加载目录", str(Path.home()))
        if not chosen:

            return False
        deps_dir = str(_normalize_deps_base_dir(Path(chosen)))
        _write_config_install_dir(cfg_path, deps_dir)

    deps_path = _normalize_deps_base_dir(Path(deps_dir))
    deps_dir = str(deps_path)
    deps_path.mkdir(parents=True, exist_ok=True)


    from PyQt6.QtWidgets import QMessageBox, QDialog
    need_install = False
    if force_enter:
        if not _find_existing_python(Path(deps_dir)):
            try:
                custom_warning_dialog("不可进入", "当前依赖目录尚未检测到可复用的 Python 环境，请先初始化依赖环境。")
            except Exception:
                print("[WARN] 缺少可复用 Python 环境，不能跳过安装直接进入。")
            return False
        _LAST_ENSURE_DEPS_FORCE_ENTER = True
        _notify_after_force_enter()
        try:
            custom_warning_dialog("警告", "缺失依赖，程序将跳过安装并进入，部分功能可能不可用。")
        except Exception:
            print("[WARN] 缺失依赖，程序将跳过安装并进入，部分功能可能不可用。")
        print("[Deps] 用户选择跳过依赖安装并进入主程序")
        return True

    is_frozen = getattr(sys, 'frozen', False)
    _DEFAULT_PYEXE_NAME = "python.exe" if os.name == "nt" else "python3"
    if is_frozen:
        # Packaged: runtime stays bundled, but dependency wizard should only treat
        # a python inside deps_dir as reusable. Missing deps python must remain
        # visible to the UI so the user can initialize it from the wizard.
        py_root = Path(deps_dir) / "python311"
        existing_pyexe = _find_existing_python(Path(deps_dir))
        pyexe = existing_pyexe or (py_root / _DEFAULT_PYEXE_NAME)
        if existing_pyexe and existing_pyexe.exists():
            print(f"[INFO] packaged: use deps python for pip: {pyexe}")
            use_bundled_python = False
        else:
            print(f"[INFO] packaged: no reusable deps python yet, wizard will initialize: {pyexe}")
            use_bundled_python = True
    else:

        py_root = Path(deps_dir) / "python311"
        existing_pyexe = _find_existing_python(Path(deps_dir))
        pyexe = existing_pyexe or (py_root / _DEFAULT_PYEXE_NAME)
        deps_dir_resolved = str(Path(deps_dir).resolve())
        mismatch_reason = ""


        is_packaged = hasattr(sys, '_MEIPASS') or '_internal' in str(Path(__file__).parent)
        mode_str = "打包模式" if is_packaged else "开发模式"

        if current_site and deps_dir and str(current_site).startswith(deps_dir_resolved):
            print(f"[INFO] {mode_str}：当前 Python 环境与依赖目录一致: {current_pyexe}")
            print(f"[DIAG] 当前 site-packages 路径: {current_site}")
            print(f"[DIAG] 依赖目录路径: {deps_dir_resolved}")
            pyexe = current_pyexe
            use_bundled_python = False
        else:
            if existing_pyexe and existing_pyexe.exists():
                use_bundled_python = False
                pyexe = existing_pyexe
                print(f"[INFO] {mode_str}：当前 Python 与依赖目录不一致，将复用目录内已有 Python: {pyexe}")
            else:
                use_bundled_python = True
                print(f"[INFO] {mode_str}：当前 Python 与依赖目录不一致，将使用独立 Python: {pyexe}")
            print(f"[DIAG] 当前 Python 解释器: {current_pyexe}")
            print(f"[DIAG] 当前 site-packages 路径: {current_site if current_site else '(未找到)'}")
            print(f"[DIAG] 依赖目录路径: {deps_dir_resolved}")
            if not current_site:
                mismatch_reason = "未能定位当前 Python 的 site-packages 路径。"
            elif not str(current_site).startswith(deps_dir_resolved):
                mismatch_reason = "当前 Python 的 site-packages 不在依赖目录下。"
            else:
                mismatch_reason = "未知原因导致环境不一致。"
            print(f"[DIAG] 环境不一致原因: {mismatch_reason}")

        if use_bundled_python and not _is_usable_python(pyexe):
            if from_settings:
                print("[INFO] 设置入口：目标依赖目录未检测到可复用 Python，先打开依赖向导，待用户确认后再初始化。")
            else:
                try:
                    if os.name != "nt":
                        # Linux / macOS: use system python3 to create a venv
                        ok = _setup_python_venv_from_system(py_root)
                        if not ok:
                            _notify_before_show_ui()
                            _exec_close_only_message_box(
                                None,
                                "未找到 Python 3",
                                _system_python_install_hint(
                                    "No reusable Python environment was detected, and no usable system python3 was found."
                                ),
                                icon=QMessageBox.Icon.Critical,
                                buttons=QMessageBox.StandardButton.Ok,
                            )
                            return False
                        pyexe = py_root / "bin" / "python3"
                        print(f"[OK] 已通过系统 Python 创建 venv: {pyexe}")
                    else:
                        installer = _find_local_python311_installer(Path(deps_dir))
                        if installer is None:
                            _notify_before_show_ui()
                            _exec_close_only_message_box(
                                None,
                                "安装器未找到",
                                "未检测到可复用 Python，且未找到本地 Python 3.11.0 安装器。\n\n"
                                "请将 `python-3.11.0-amd64.exe` 放到依赖目录、程序目录下的 `_internal`，或项目根目录后重试。",
                                icon=QMessageBox.Icon.Critical,
                                buttons=QMessageBox.StandardButton.Ok,
                            )
                            return False
                        print(f"[INFO] 未找到私有 Python，将调用本地安装器: {installer}")
                        _notify_before_show_ui()
                        ok = _run_local_python311_installer(installer, py_root, before_launch=_notify_before_show_ui)
                        if not ok or not _is_usable_python(pyexe):
                            _notify_before_show_ui()
                            _exec_close_only_message_box(
                                None,
                                "安装失败",
                                "Python 3.11.0 安装失败。\n\n"
                                f"请确认已通过本地安装器安装到以下目录：\n{py_root}",
                                icon=QMessageBox.Icon.Critical,
                                buttons=QMessageBox.StandardButton.Ok,
                            )
                            return False
                        print(f"[OK] 已安装私有 Python: {pyexe}")
                except Exception as e:
                    print(f"[ERR] 自动安装 Python 失败: {e}")
                    _notify_before_show_ui()
                    _exec_close_only_message_box(
                        None,
                        "安装失败",
                        f"调用本地 Python 安装器失败：{e}",
                        icon=QMessageBox.Icon.Critical,
                        buttons=QMessageBox.StandardButton.Ok,
                    )
                    return False


    try:
        _ensure_pip(pyexe)
        state_path = Path(deps_dir) / STATE_FILE
        if not state_path.exists():
            _save_json(state_path, {"installed_layers": []})
        pip_ready_event.set()
    except Exception as e:
        print(f"[Deps] 预初始化 pip 失败: {e}")
        pip_ready_event.set()

    import platform
    print("【依赖目录选择后环境信息】")
    print("主进程解释器:", current_pyexe)
    print("主进程平台:", platform.platform())
    print("主进程 sys.path:", sys.path)
    print("目标依赖解释器:", pyexe)
    print("目标依赖目录:", deps_dir)

    def _apply_runtime_context(active_pyexe: Path) -> None:
        sp_local = _site_packages_root(active_pyexe)

        if (
            os.environ.get("LATEXSNIPPER_BOOTSTRAPPED") != "1"
            and active_pyexe is not None
            and active_pyexe.exists()
        ):
            _inject_private_python_paths(active_pyexe)
        os.environ["LATEX_SNIPPER_SITE"] = str(sp_local or "")
        if active_pyexe is not None and active_pyexe.exists():
            os.environ["LATEXSNIPPER_PYEXE"] = str(active_pyexe)
        os.environ["LATEXSNIPPER_INSTALL_BASE_DIR"] = str(deps_path)
        os.environ["LATEXSNIPPER_DEPS_DIR"] = str(deps_path)

    _apply_runtime_context(pyexe)

    state_path = deps_path / STATE_FILE
    state = _sanitize_state_layers(state_path)
    installed = {"layers": state.get("installed_layers", [])}

    state_path = deps_path / STATE_FILE

    needed = {required_layer for required_layer in require_layers if required_layer in LAYER_MAP}

    def _missing_required_layers(layer_list: list[str]) -> list[str]:
        missing = [layer for layer in needed if layer not in layer_list]
        if not any(layer in layer_list for layer in MATHCRAFT_RUNTIME_LAYERS):
            missing.append("MATHCRAFT_CPU")
        return missing

    def _deps_ready(layer_list: list[str]) -> bool:
        return not _missing_required_layers(layer_list)

    missing_layers = _missing_required_layers(installed["layers"])
    skip_next_ui_runtime_verify = False

    def _default_selected_layers(installed_layers_list: list[str], failed_layers_list: list[str] | None = None) -> list[str]:
        defaults = ["BASIC", "CORE"]
        installed_set = {str(x) for x in (installed_layers_list or [])}
        failed_set = {str(x) for x in (failed_layers_list or [])}
        runtime_present = any(x in set(MATHCRAFT_RUNTIME_LAYERS) for x in (installed_set | failed_set))
        if not runtime_present:
            defaults.append("MATHCRAFT_CPU")
        return defaults

    def _reverify_installed_layers_if_needed(reason: str = "") -> bool:
        """Reverify installed layers when needed before entering the app."""
        nonlocal state, installed, missing_layers
        if not from_settings:
            return _deps_ready(installed["layers"])
        if not pyexe or not os.path.exists(pyexe):
            return _deps_ready(installed["layers"])

        claimed = [layer for layer in installed.get("layers", []) if layer in LAYER_MAP]
        if not claimed:
            missing_layers = _missing_required_layers(installed["layers"])
            return _deps_ready(installed["layers"])

        if reason:
            print(f"[INFO] 触发已安装层复验: {reason}")
        print("[INFO] 从设置入口复验已安装功能层...")
        verified = _verify_installed_layers(
            str(pyexe),
            claimed,
            log_fn=lambda m: print(m),
        )
        failed = [layer for layer in claimed if layer not in verified]
        payload = {"installed_layers": verified}
        if failed:
            payload["failed_layers"] = failed
        _save_json(state_path, payload)

        state = payload
        installed["layers"] = verified
        missing_layers = _missing_required_layers(installed["layers"])
        if failed:
            print(f"[WARN] 复验失败层: {', '.join(failed)}")
        return _deps_ready(installed["layers"])

    def _switch_deps_context(target_deps_dir: str) -> tuple[list[str], bool]:
        nonlocal deps_dir, deps_path, state_path, state, installed, missing_layers, pyexe
        deps_dir = str(_normalize_deps_base_dir(Path(target_deps_dir or deps_dir)))
        deps_path = Path(deps_dir)
        py_root = deps_path / "python311"
        existing_pyexe = _find_existing_python(deps_path)
        if is_frozen:
            pyexe = existing_pyexe or (py_root / _DEFAULT_PYEXE_NAME)
            use_bundled = not (existing_pyexe and existing_pyexe.exists())
        else:
            deps_dir_resolved = str(deps_path.resolve())
            if current_site and str(current_site).startswith(deps_dir_resolved):
                pyexe = current_pyexe
                use_bundled = False
            elif existing_pyexe and existing_pyexe.exists():
                pyexe = existing_pyexe
                use_bundled = False
            else:
                pyexe = py_root / _DEFAULT_PYEXE_NAME
                use_bundled = True
        _apply_runtime_context(pyexe)
        state_path = deps_path / STATE_FILE
        state = _sanitize_state_layers(state_path)
        installed["layers"] = state.get("installed_layers", [])
        missing_layers = _missing_required_layers(installed["layers"])
        return missing_layers, use_bundled

    while True:
        if (missing_layers and prompt_ui) or always_show_ui:
            stop_event = threading.Event()

            default_select = _default_selected_layers(
                installed.get("layers", []),
                state.get("failed_layers", []),
            )

            chosen = []
            dlg, chosen = _build_layers_ui(
                pyexe,
                deps_dir,
                installed,
                default_select,
                chosen,
                state_path,
                from_settings=from_settings,
                skip_runtime_verify_once=skip_next_ui_runtime_verify
            )
            skip_next_ui_runtime_verify = False
            _notify_before_show_ui()
            result = dlg.exec()
            if result != dlg.DialogCode.Accepted:

                return False

            chosen_layers = _normalize_chosen_layers(chosen.get("layers", []))
            mirror_source = str(chosen.get("mirror_source", "")).strip().lower()
            if mirror_source in ("off", "tuna"):
                use_mirror = (mirror_source == "tuna")
            else:
                use_mirror = bool(chosen.get("mirror", False))
                mirror_source = "tuna" if use_mirror else "off"
            missing_layers, use_bundled_python = _switch_deps_context(chosen.get("deps_path", deps_dir))


            if chosen.get("force_enter", False):
                _LAST_ENSURE_DEPS_FORCE_ENTER = True
                _notify_after_force_enter()
                print("[INFO] 用户选择跳过依赖安装并进入主程序")
                return True
            if chosen.get("action") == "enter":
                print("[INFO] 用户选择直接进入主程序。")
                return True
            if chosen["layers"]:
                failed_claims = {
                    str(x) for x in (state.get("failed_layers", []) if isinstance(state, dict) else [])
                }
                already_have = all(
                    layer in state.get("installed_layers", []) for layer in chosen["layers"]
                )
                has_failed_choice = any(layer in failed_claims for layer in chosen["layers"])
                if already_have and not has_failed_choice:
                    if not chosen.get("verified_in_ui", False) and not _reverify_installed_layers_if_needed("skip_download_already_have"):
                        print("[WARN] 复验后关键层不完整，返回向导。")
                        continue
                    print("[INFO] 所选层已存在，跳过下载。")
                    return True

            print(f"[INFO] 依赖下载源: {'清华镜像' if use_mirror else '官方 PyPI'} ({mirror_source})")
            py_root = deps_path / "python311"
            need_install = bool(chosen_layers) and bool(missing_layers)
            need_install = bool(chosen_layers)

        if need_install:
            if chosen_layers:
                if use_bundled_python and not _is_usable_python(Path(pyexe)):
                    if os.name != "nt":
                        # Linux / macOS: use system python3 to create a venv
                        ok = _setup_python_venv_from_system(py_root)
                        if not ok:
                            _notify_before_show_ui()
                            _exec_close_only_message_box(
                                None,
                                "未找到 Python 3",
                                _system_python_install_hint(
                                    "No usable system python3 was found, so the dependency environment cannot be initialized."
                                ),
                                icon=QMessageBox.Icon.Critical,
                                buttons=QMessageBox.StandardButton.Ok,
                            )
                            always_show_ui = True
                            continue
                        pyexe = py_root / "bin" / "python3"
                        print(f"[OK] 已通过系统 Python 创建 venv: {pyexe}")
                    else:
                        installer = _find_local_python311_installer(deps_path)
                        if installer is None:
                            _notify_before_show_ui()
                            _exec_close_only_message_box(
                                None,
                                "安装器未找到",
                                "目标依赖目录未检测到可复用 Python，且未找到本地安装器。\n\n"
                                "请将 `python-3.11.0-amd64.exe` 放到依赖目录、程序目录下的 `_internal`，或项目根目录后重试。",
                                icon=QMessageBox.Icon.Critical,
                                buttons=QMessageBox.StandardButton.Ok,
                            )
                            always_show_ui = True
                            continue

                        _notify_before_show_ui()
                        confirm = _exec_close_only_message_box(
                            None,
                            "初始化依赖环境",
                            "目标依赖目录未检测到可复用 Python 环境。\n\n"
                            f"是否现在初始化以下目录后继续安装依赖？\n{py_root}",
                            icon=QMessageBox.Icon.Question,
                            buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                            default_button=QMessageBox.StandardButton.Yes,
                        )
                        if confirm != QMessageBox.StandardButton.Yes:
                            always_show_ui = True
                            continue

                        _notify_before_show_ui()
                        ok = _run_local_python311_installer(installer, py_root, before_launch=_notify_before_show_ui)
                        if not ok or not _is_usable_python(Path(pyexe)):
                            _notify_before_show_ui()
                            _exec_close_only_message_box(
                                None,
                                "安装失败",
                                "Python 3.11.0 安装失败。\n\n"
                                f"请确认已通过本地安装器安装到以下目录：\n{py_root}",
                                icon=QMessageBox.Icon.Critical,
                                buttons=QMessageBox.StandardButton.Ok,
                            )
                            always_show_ui = True
                            continue
                    try:
                        _ensure_pip(pyexe)
                    except Exception as e:
                        print(f"[Deps] 初始化目标 Python 后确保 pip 失败: {e}")

                RESULT_BACK_TO_WIZARD = 1001
                if "MATHCRAFT_GPU" in chosen_layers and not _gpu_available():
                    r = _exec_close_only_message_box(
                        None,
                        "GPU 未检测",
                        "未检测到 NVIDIA GPU，继续安装 onnxruntime-gpu 可能无法启用 CUDAExecutionProvider，是否继续？",
                        icon=QMessageBox.Icon.Question,
                        buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        default_button=QMessageBox.StandardButton.No,
                    )
                    if r != QMessageBox.StandardButton.Yes:
                        chosen_layers = [c for c in chosen_layers if c != "MATHCRAFT_GPU"]

                if "CORE" in chosen_layers and not any(layer in chosen_layers for layer in MATHCRAFT_RUNTIME_LAYERS):
                    chosen_layers = list(chosen_layers) + ["MATHCRAFT_CPU"]
                    print("[INFO] CORE 未指定 MathCraft 后端，已自动补充 MATHCRAFT_CPU")

                pkgs = []
                for layer in chosen_layers:
                    pkgs.extend(LAYER_MAP[layer])

                if "MATHCRAFT_GPU" in chosen_layers:
                    pkgs = [p for p in pkgs if not (p.lower().startswith("onnxruntime") and "gpu" not in p.lower())]
                elif "MATHCRAFT_CPU" in chosen_layers:
                    pkgs = [p for p in pkgs if not p.lower().startswith("onnxruntime-gpu")]

                pkgs = _filter_packages(pkgs)
                log_q = queue.Queue()
                stop_event = threading.Event()
                pause_event = threading.Event()
                state_lock = threading.Lock()

                dlg, info, logw, btn_cancel, btn_pause, progress = _progress_dialog()
                from PyQt6 import sip
                ui_closed = {"value": False}
                timer_holder = {"log": None, "speed": None}
                verify_worker_holder = {"obj": None}
                post_install_verify_passed = {"value": False}
                paused = False
                net_speed_state = {
                    "busy": False,
                    "base_text": "",
                    "last_sample": None,
                    "down_bps": None,
                    "pip_speed_text": "",
                    "pip_eta_text": "",
                    "pip_progress_text": "",
                }

                def _is_alive(obj):
                    try:
                        return obj is not None and not sip.isdeleted(obj)
                    except Exception:
                        return False

                def _append_log(text: str):
                    if _is_alive(logw):
                        try:
                            logw.append(text)
                        except RuntimeError:
                            pass

                def _set_progress(val: int):
                    if _is_alive(progress):
                        try:
                            progress.setValue(int(val))
                        except RuntimeError:
                            pass

                def _format_speed(bytes_per_sec):
                    try:
                        speed = float(bytes_per_sec)
                    except Exception:
                        return ""
                    if speed < 1024:
                        return f"{speed:.0f} B/s"
                    if speed < 1024 * 1024:
                        return f"{speed / 1024:.1f} KB/s"
                    if speed < 1024 * 1024 * 1024:
                        return f"{speed / (1024 * 1024):.1f} MB/s"
                    return f"{speed / (1024 * 1024 * 1024):.2f} GB/s"

                def _render_info_text():
                    text = net_speed_state.get("base_text", "") or ""
                    if net_speed_state.get("busy", False):
                        pip_speed = (net_speed_state.get("pip_speed_text") or "").strip()
                        pip_eta = (net_speed_state.get("pip_eta_text") or "").strip()
                        pip_progress = (net_speed_state.get("pip_progress_text") or "").strip()
                        if pip_speed:
                            text = f"{text}  下载速度：{pip_speed}"
                            if pip_eta:
                                text = f"{text}  剩余：{pip_eta}"
                            if pip_progress:
                                text = f"{text}  {pip_progress}"
                        else:
                            speed = net_speed_state.get("down_bps")
                            if speed is not None:
                                text = f"{text}  下载速度：{_format_speed(speed)}"
                            else:
                                text = f"{text}  下载速度：计算中..."
                    if _is_alive(info):
                        try:
                            info.setText(text)
                        except RuntimeError:
                            pass

                def _parse_pip_transfer_status(line: str):
                    if not line:
                        return None
                    text = line.strip().replace("\r", " ")
                    if not text:
                        return None
                    speed_match = re.search(r"(\d+(?:\.\d+)?)\s*([kmg]?i?B/s)", text, re.IGNORECASE)
                    if not speed_match:
                        return None
                    speed_text = f"{speed_match.group(1)} {speed_match.group(2)}"
                    eta_match = re.search(r"(\d+:\d{2}:\d{2}|\d+:\d{2})", text)
                    progress_match = re.search(
                        r"(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*([kmg]?i?B)",
                        text,
                        re.IGNORECASE,
                    )
                    progress_text = ""
                    if progress_match:
                        progress_text = (
                            f"{progress_match.group(1)}/{progress_match.group(2)} {progress_match.group(3)}"
                        )
                    return {
                        "speed_text": speed_text,
                        "eta_text": eta_match.group(1) if eta_match else "",
                        "progress_text": progress_text,
                    }

                def _sample_network_speed():
                    if psutil is None or not net_speed_state.get("busy", False):
                        return
                    try:
                        counters = psutil.net_io_counters()
                    except Exception:
                        return
                    if counters is None:
                        return
                    now = time.monotonic()
                    current = (now, int(getattr(counters, "bytes_recv", 0)))
                    last = net_speed_state.get("last_sample")
                    net_speed_state["last_sample"] = current
                    if last is None:
                        net_speed_state["down_bps"] = None
                        _render_info_text()
                        return
                    elapsed = max(0.001, current[0] - last[0])
                    delta = max(0, current[1] - last[1])
                    net_speed_state["down_bps"] = delta / elapsed
                    _render_info_text()

                def _set_info_text(text: str):
                    net_speed_state["base_text"] = text or ""
                    _render_info_text()

                def _set_network_speed_busy(is_busy: bool):
                    net_speed_state["busy"] = bool(is_busy)
                    net_speed_state["last_sample"] = None
                    net_speed_state["down_bps"] = None
                    net_speed_state["pip_speed_text"] = ""
                    net_speed_state["pip_eta_text"] = ""
                    net_speed_state["pip_progress_text"] = ""
                    _render_info_text()

                def toggle_pause():
                    nonlocal paused
                    paused = not paused
                    if paused:
                        pause_event.clear()
                        btn_pause.setText("继续下载")
                    else:
                        pause_event.set()
                        btn_pause.setText("暂停下载")

                btn_pause.clicked.connect(toggle_pause)
                pause_event.set()


                worker = InstallWorker(
                    pyexe, pkgs, stop_event, pause_event, state_lock, state, state_path,
                    chosen_layers, log_q, mirror=use_mirror,
                    force_reinstall=False, no_cache=False
                )

                def request_cancel():
                    ui_closed["value"] = True
                    stop_event.set()
                    for t in timer_holder.values():
                        if t is not None:
                            try:
                                t.stop()
                            except Exception:
                                pass
                    try:
                        if worker.isRunning():
                            worker.stop()
                    except Exception:
                        pass
                    if _is_alive(dlg):
                        try:
                            dlg.reject()
                        except RuntimeError:
                            pass

                btn_cancel.clicked.connect(request_cancel)

                worker.log_updated.connect(_append_log)
                worker.progress_updated.connect(_set_progress)
                worker.status_updated.connect(_set_info_text)
                worker.busy_state_changed.connect(_set_network_speed_busy)

                def _finalize_done_ui():
                    _set_network_speed_busy(False)
                    if _is_alive(progress):
                        _set_progress(progress.maximum())
                    if _is_alive(btn_cancel):
                        btn_cancel.setText("完成")
                    if _is_alive(btn_pause):
                        btn_pause.setEnabled(False)
                    if _is_alive(btn_cancel):
                        try:
                            btn_cancel.clicked.disconnect()
                        except Exception:
                            pass
                        btn_cancel.clicked.connect(
                            lambda: dlg.done(RESULT_BACK_TO_WIZARD) if _is_alive(dlg) else None
                        )
                    try:
                        if hasattr(dlg, "refresh_ui"):
                            dlg.refresh_ui()
                    except Exception as e:
                        print(f"[WARN] refresh ui failed: {e}")

                def on_install_done(success: bool):
                    if ui_closed["value"] or stop_event.is_set() or (not _is_alive(dlg)):
                        return

                    if not success:
                        _append_log("\n[ERR] Install has failures, check logs ❌")
                        if _is_alive(dlg):
                            _exec_close_only_message_box(
                                dlg,
                                "Install Incomplete",
                                "Some dependencies failed to install. Please check logs and retry.",
                                icon=QMessageBox.Icon.Warning,
                                buttons=QMessageBox.StandardButton.Ok,
                            )
                        _finalize_done_ui()
                        return

                    _append_log("\n[INFO] 正在后台验证已安装功能层...")
                    _set_info_text("依赖下载完成，正在后台验证功能层...")

                    verify_worker = LayerVerifyWorker(pyexe, chosen_layers, state_path)
                    verify_worker_holder["obj"] = verify_worker
                    verify_worker.log_updated.connect(_append_log)

                    def on_verify_done(_ok_layers: list, fail_layers: list):
                        if ui_closed["value"] or (not _is_alive(dlg)):
                            return
                        post_install_verify_passed["value"] = not bool(fail_layers)
                        if fail_layers:
                            _append_log(f"\n[WARN] Layers installed but verify failed: {', '.join(fail_layers)}")
                            _exec_close_only_message_box(
                                dlg,
                                "部分验证失败",
                                f"以下功能层安装但无法正常工作:\n{', '.join(fail_layers)}\n\n请查看日志或使用【打开环境终端】手动修复。",
                                icon=QMessageBox.Icon.Warning,
                                buttons=QMessageBox.StandardButton.Ok,
                            )
                        else:
                            _exec_close_only_message_box(
                                dlg,
                                "安装完成",
                                "所有依赖已安装并验证通过！点击完成返回依赖向导。",
                                icon=QMessageBox.Icon.Information,
                                buttons=QMessageBox.StandardButton.Ok,
                            )
                        _finalize_done_ui()

                    verify_worker.done.connect(on_verify_done)
                    verify_worker.start()

                worker.done.connect(on_install_done)


                timer = QTimer(dlg)
                timer_holder["log"] = timer
                timer.setInterval(50)

                def drain_log_queue():
                    drained = 0
                    lines_to_emit = []
                    while drained < 50:
                        try:
                            line = log_q.get_nowait()
                        except queue.Empty:
                            break
                        else:
                            lines_to_emit.append(line)
                            drained += 1
                    if lines_to_emit:
                        for line in lines_to_emit:
                            parsed_transfer = _parse_pip_transfer_status(line)
                            if parsed_transfer:
                                net_speed_state["pip_speed_text"] = parsed_transfer["speed_text"]
                                net_speed_state["pip_eta_text"] = parsed_transfer["eta_text"]
                                net_speed_state["pip_progress_text"] = parsed_transfer["progress_text"]
                                _render_info_text()
                        _append_log("\n".join(lines_to_emit))

                timer.timeout.connect(drain_log_queue)
                timer.start()

                speed_timer = QTimer(dlg)
                timer_holder["speed"] = speed_timer
                speed_timer.setInterval(1000)
                speed_timer.timeout.connect(_sample_network_speed)
                speed_timer.start()

                def on_close_event(event):
                    ui_closed["value"] = True
                    try:
                        for t in timer_holder.values():
                            if t is not None:
                                t.stop()
                        try:
                            worker.log_updated.disconnect(_append_log)
                        except Exception:
                            pass
                        try:
                            worker.progress_updated.disconnect(_set_progress)
                        except Exception:
                            pass
                        try:
                            worker.done.disconnect(on_install_done)
                        except Exception:
                            pass
                        vw = verify_worker_holder.get("obj")
                        if vw is not None:
                            try:
                                vw.log_updated.disconnect(_append_log)
                            except Exception:
                                pass
                            try:
                                vw.done.disconnect()
                            except Exception:
                                pass
                            try:
                                if vw.isRunning():
                                    vw.wait(3000)
                            except Exception:
                                pass
                        worker.stop()
                        worker.wait(5000)
                    except Exception as e:
                        print(f"[WARN] 关闭事件清理异常: {e}")
                    finally:
                        event.accept()

                dlg.closeEvent = on_close_event

                worker.start()
                result = dlg.exec()
                if worker.isRunning():
                    worker.stop()
                    worker.wait(3000)
                vw = verify_worker_holder.get("obj")
                if vw is not None and vw.isRunning():
                    vw.wait(3000)

                install_verified_in_progress_ui = bool(post_install_verify_passed.get("value", False))
                if result == RESULT_BACK_TO_WIZARD:
                    try:
                        state = _sanitize_state_layers(state_path)
                        installed["layers"] = state.get("installed_layers", [])
                        missing_layers = _missing_required_layers(installed["layers"])
                    except Exception:
                        pass
                    skip_next_ui_runtime_verify = install_verified_in_progress_ui
                    always_show_ui = True
                    continue
                if result != QDialog.DialogCode.Accepted:

                    skip_next_ui_runtime_verify = install_verified_in_progress_ui
                    continue
        break
    return True
