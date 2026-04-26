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

_LAST_ENSURE_DEPS_FORCE_ENTER = False


def was_last_ensure_deps_force_enter():
    return _LAST_ENSURE_DEPS_FORCE_ENTER


try:
    from PyQt6.QtCore import QThread, pyqtSignal
    from PyQt6.QtCore import QTimer
    from PyQt6.QtGui import QIcon
except Exception:
    class _Signal:
        def __init__(self):
            self._handlers = []

        def connect(self, fn):
            if callable(fn) and fn not in self._handlers:
                self._handlers.append(fn)

        def disconnect(self, fn):
            try:
                self._handlers.remove(fn)
            except ValueError:
                pass

        def emit(self, *args, **kwargs):
            for fn in list(self._handlers):
                try:
                    fn(*args, **kwargs)
                except Exception:
                    pass

    class _SignalDescriptor:
        def __set_name__(self, _owner, name):
            self._name = f"__sig_{name}"

        def __get__(self, instance, _owner):
            if instance is None:
                return self
            sig = instance.__dict__.get(self._name)
            if sig is None:
                sig = _Signal()
                instance.__dict__[self._name] = sig
            return sig

    def pyqtSignal(*_args, **_kwargs):
        return _SignalDescriptor()

    class QThread:
        def __init__(self, *args, **kwargs):
            super().__init__()
            self._thread = None
            self._running = False

        def start(self):
            if self._thread and self._thread.is_alive():
                return

            def _runner():
                try:
                    self._running = True
                    self.run()
                finally:
                    self._running = False

            self._thread = threading.Thread(target=_runner, daemon=True)
            self._thread.start()

        def run(self):
            pass

        def isRunning(self):
            return bool(self._thread and self._thread.is_alive())

        def wait(self, timeout_ms=None):
            if not self._thread:
                return True
            timeout_s = None
            if timeout_ms is not None:
                try:
                    timeout_s = max(0.0, float(timeout_ms) / 1000.0)
                except Exception:
                    timeout_s = None
            self._thread.join(timeout=timeout_s)
            return not self._thread.is_alive()

    class QTimer:
        def __init__(self, *_args, **_kwargs):
            self.timeout = _Signal()

        def start(self, *_args, **_kwargs):
            return

        def stop(self):
            return

        @staticmethod
        def singleShot(_ms, fn):
            if callable(fn):
                try:
                    fn()
                except Exception:
                    pass

    class QIcon:
        def __init__(self, *_args, **_kwargs):
            pass

try:
    import psutil
except Exception:
    psutil = None

subprocess_lock = threading.Lock()

def safe_run(cmd, cwd=None, shell=False, timeout=None, **popen_kwargs):
    """
    启动子进程并返回 Popen 对象，不预先读取/关闭 stdout。
    透传一切 Popen 参数（如 stdout/stderr/text/encoding/env/bufsize/creationflags 等），
    让调用方（例如 _pip_install）自己控制读取和等待。
    """
    print(f"[RUN] {' '.join(cmd)}")
    # 默认按行读取：如果调用方没指定，给个合理的默认
    popen_kwargs.setdefault("stdout", subprocess.PIPE)
    popen_kwargs.setdefault("stderr", subprocess.STDOUT)
    popen_kwargs.setdefault("text", True)
    if sys.platform == "win32":
        popen_kwargs.setdefault("creationflags", flags)

    # 直接 Popen，剩下的读取/等待由调用方处理
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
    done = pyqtSignal(bool)  # True=全部成功

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
        self.log_q = log_q  # 新增

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
        """用于从UI触发中断下载"""
        self.stop_event.set()
        if hasattr(self, "proc") and self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:
                pass
            finally:
                self.proc = None


    def run(self):
        """依赖安装线程主函数：MathCraft v1 只管理 ONNX Runtime 后端。"""
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
                if root_name == "onnxruntime-gpu":
                    return ORT_GPU_DEFAULT_SPEC
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

            if not pending:
                self.log_updated.emit("[INFO] 所有依赖已安装，无需下载。")
                self.progress_updated.emit(100)
                self._emit_done_safe(True)
                return

            self.log_updated.emit(f"[INFO] 需要安装 {len(pending)} 个包（跳过 {len(skipped)} 个已安装）")

            total = len(pending)
            done_count = 0
            fail_count = 0
            failed_pkgs = []

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
                percent = int(done_count / total * 100)
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

            _fix_critical_versions(self.pyexe, self.log_updated.emit, use_mirror=self.mirror)

            runtime_ort_ok = True
            runtime_ort_err = ""
            if want_gpu_runtime:
                runtime_ort_ok, runtime_ort_err = _repair_gpu_onnxruntime_runtime(
                    self.pyexe,
                    ORT_GPU_DEFAULT_SPEC,
                    self.stop_event,
                    self.pause_event,
                    self.log_q,
                    use_mirror=self.mirror,
                    force_reinstall=self.force_reinstall,
                    no_cache=self.no_cache,
                    proc_setter=lambda p: setattr(self, "proc", p),
                )
                if runtime_ort_ok:
                    self.log_updated.emit("[OK] onnxruntime-gpu runtime check passed ✅")
                else:
                    self.log_updated.emit(f"[WARN] onnxruntime-gpu runtime still invalid: {runtime_ort_err[:400]}")
            elif want_cpu_runtime:
                runtime_ort_ok, runtime_ort_err = _verify_onnxruntime_runtime(
                    self.pyexe, expect_gpu=False, timeout=45
                )
                if runtime_ort_ok:
                    self.log_updated.emit("[OK] onnxruntime CPU runtime check passed ✅")
                else:
                    self.log_updated.emit(f"[WARN] onnxruntime CPU runtime invalid: {runtime_ort_err[:400]}")

            all_ok = (fail_count == 0) and runtime_ort_ok

            if all_ok:
                self.log_updated.emit("[OK] 所有依赖安装成功 ✅")
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

        try:
            state = _load_json(self.state_path, {"installed_layers": []})
            current_layers = set(state.get("installed_layers", []))
            current_layers.update(verify_ok_layers)
            # MathCraft ONNX 后端互斥：成功写回时只保留一个。
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
    # 后台安装/校验流程始终隐藏子进程窗口，避免终端闪烁影响体验。
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

ORT_CPU_SPEC = "onnxruntime~=1.19.2"
ORT_GPU_DEFAULT_SPEC = "onnxruntime-gpu~=1.19.2"
pip_ready_event = threading.Event()
PIP_INSTALL_SUPPRESS_ARGS = ["--no-warn-script-location"]
# ONNX Runtime 支撑包版本约束，避免 pip 解析带入不可用组合。
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


def _fix_critical_versions(pyexe: str, log_fn=None, use_mirror: bool = False) -> bool:
    """
    安装完成后强制修复关键依赖版本。
    """
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
            # 使用 --no-deps 避免触发依赖解析
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
            log_fn("[OK] ONNX Runtime 关键依赖导入检查通过")
        else:
            log_fn(f"[WARN] ONNX Runtime 关键依赖仍不可用: {err[:400]}")
    return ok

# 各功能层的运行时验证测试代码
_CORE_VERIFY_CODE = """
import importlib.util

for mod in ("transformers", "rapidocr", "cv2", "PIL", "latex2mathml.converter", "matplotlib", "fitz"):
    if importlib.util.find_spec(mod) is None:
        raise RuntimeError(f"{mod} not installed")

print("CORE OK")
"""

LAYER_VERIFY_CODE = {
    "BASIC": """
import PIL
import requests
import lxml
print("BASIC OK")
""",
    "CORE": _CORE_VERIFY_CODE,
    "MATHCRAFT_CPU": """
import onnxruntime as ort
providers = ort.get_available_providers()
if "CPUExecutionProvider" not in providers:
    raise RuntimeError(f"CPUExecutionProvider unavailable: {providers}")
print("ONNX providers:", providers)
print("MATHCRAFT_CPU OK")
""",
    "MATHCRAFT_GPU": """
import onnxruntime as ort
providers = ort.get_available_providers()
if "CUDAExecutionProvider" not in providers:
    raise RuntimeError(f"CUDAExecutionProvider unavailable: {providers}")
print("ONNX providers:", providers)
print("MATHCRAFT_GPU OK")
""",
}

# 严格验证（会触发真实模型加载/推理），仅在强制验证时启用
def _verify_layer_runtime(pyexe: str, layer: str, timeout: int = 60) -> tuple:
    """
    验证某个功能层是否能在运行时正常工作。
    
    返回: (success: bool, error_msg: str)
    """
    import subprocess
    
    if layer == "CORE":
        timeout = max(timeout, 120)

    if layer in LAYER_VERIFY_CODE:
        code = LAYER_VERIFY_CODE[layer]
    else:
        # 没有验证代码的层，默认通过
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
            # 提取关键错误信息
            err = (result.stderr or result.stdout or "").strip()
            if not err:
                err = f"验证进程返回码 {result.returncode}，但无可用输出"
            # 截取最后几行，通常是最有用的
            err_lines = err.replace("\r", "").split('\n')[-15:]
            return False, '\n'.join(err_lines)
    except subprocess.TimeoutExpired:
        return False, "验证超时"
    except Exception as e:
        return False, str(e)

def _verify_installed_layers(pyexe: str, claimed_layers: list, log_fn=None) -> list:
    """
    验证声称已安装的层是否真正可用。
    
    返回: 真正可用的层列表
    """
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
    return verified



def _verify_onnxruntime_runtime(pyexe: str, expect_gpu: bool = False, timeout: int = 30) -> tuple[bool, str]:
    """
    验证 onnxruntime 运行时可用性。
    - 必须存在 get_available_providers
    - GPU 场景必须包含 CUDAExecutionProvider
    """
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
        return False
    try:
        subprocess.run(
            [str(pyexe), "-m", "pip", "uninstall", pkg_key, "-y"],
            timeout=timeout,
            check=False,
            creationflags=flags
        )
        current.pop(pkg_key, None)
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


# MathCraft v1 分层依赖：识别运行时只区分 ONNX CPU/GPU 后端。
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
}

MATHCRAFT_RUNTIME_LAYERS = ("MATHCRAFT_CPU", "MATHCRAFT_GPU")

# ---------------- 基础工具 ----------------
def _load_json(p: Path, default):
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default

def _save_json(p: Path, data, log_q=None):
    try:
        from pathlib import Path
        Path(p).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        msg = f"[Deps] 写文件失败: {e}"
        print(msg)
        if log_q:
            log_q.put(msg)

def _sanitize_state_layers(state_path: Path, state: dict | None = None) -> dict:
    """规范化层状态：移除未知层，并保证 MathCraft CPU/GPU 后端互斥。"""
    if state is None:
        state = _load_json(state_path, {"installed_layers": []})

    raw_installed = state.get("installed_layers", [])
    raw_failed = state.get("failed_layers", [])

    if not isinstance(raw_installed, list):
        raw_installed = []
    if not isinstance(raw_failed, list):
        raw_failed = []

    installed = [layer for layer in raw_installed if layer in LAYER_MAP]
    failed = [layer for layer in raw_failed if layer in LAYER_MAP]

    present_runtime = {x for x in MATHCRAFT_RUNTIME_LAYERS if x in installed or x in failed}
    if len(present_runtime) > 1:
        if "MATHCRAFT_GPU" in installed and "MATHCRAFT_CPU" not in installed:
            keep_runtime = "MATHCRAFT_GPU"
        elif "MATHCRAFT_CPU" in installed and "MATHCRAFT_GPU" not in installed:
            keep_runtime = "MATHCRAFT_CPU"
        elif "MATHCRAFT_GPU" in failed and "MATHCRAFT_CPU" not in failed:
            keep_runtime = "MATHCRAFT_GPU"
        elif "MATHCRAFT_CPU" in failed and "MATHCRAFT_GPU" not in failed:
            keep_runtime = "MATHCRAFT_CPU"
        else:
            keep_runtime = "MATHCRAFT_GPU"
        installed = [layer for layer in installed if layer not in MATHCRAFT_RUNTIME_LAYERS or layer == keep_runtime]
        failed = [layer for layer in failed if layer not in MATHCRAFT_RUNTIME_LAYERS or layer == keep_runtime]

    changed = (installed != raw_installed) or (failed != raw_failed)
    payload = {"installed_layers": installed}
    if failed:
        payload["failed_layers"] = failed

    if changed:
        _save_json(state_path, payload)
        dropped = sorted(set(raw_installed + raw_failed) - set(installed + failed))
        if dropped:
            print(f"[INFO] 已忽略并移除废弃/未知层: {', '.join(dropped)}")

    return payload


def _normalize_chosen_layers(layers: list[str] | None) -> list[str]:
    """Normalize selected layers and enforce MathCraft CPU/GPU backend mutual exclusion."""
    ordered: list[str] = []
    seen: set[str] = set()
    for layer in (layers or []):
        name = str(layer)
        if name not in LAYER_MAP or name in seen:
            continue
        if name == "MATHCRAFT_CPU" and "MATHCRAFT_GPU" in seen:
            continue
        if name == "MATHCRAFT_GPU" and "MATHCRAFT_CPU" in seen:
            ordered = [x for x in ordered if x != "MATHCRAFT_CPU"]
            seen.discard("MATHCRAFT_CPU")
        ordered.append(name)
        seen.add(name)
    return ordered

def _site_packages_root(pyexe: Path):
    """
    传入的是 python.exe 路径：
      - 独立版: <deps_dir>/python311/python.exe -> <deps_dir>/python311/Lib/site-packages
      - venv 版: <deps_dir>/venv/Scripts/python.exe -> <deps_dir>/venv/Lib/site-packages
    """
    py_dir = pyexe.parent
    # 支持 .venv/Scripts/python.exe 结构，向上查找 Lib/site-packages
    candidates = [
        py_dir / "Lib" / "site-packages",
        py_dir.parent / "Lib" / "site-packages",
        py_dir.parent.parent / "Lib" / "site-packages",
    ]
    for sp in candidates:
        if sp.exists():
            return sp
    return None

def _inject_private_python_paths(pyexe: Path):
    """
    仅在开发模式下注入私有 site-packages 路径。
    打包后的程序：AI 模型在子进程中运行，无需注入。
    """
    import os
    import sys
    
    # 打包模式下不注入，避免与内置包冲突
    is_frozen = getattr(sys, 'frozen', False)
    if is_frozen:
        print("[INFO] 打包模式：跳过路径注入，AI 模型将在子进程中使用独立 Python")
        return
    
    sp = _site_packages_root(pyexe)
    if not sp:
        return

    # 1) 剔除 venv/项目 site-packages，避免环境混用
    bad_markers = [
        os.sep + ".venv" + os.sep,
        os.sep + "env" + os.sep,
        os.sep + "venv" + os.sep,
    ]
    sys.path[:] = [p for p in sys.path if not any(m in p for m in bad_markers)]
    # 2) 把私有 site-packages 放到最前
    if str(sp) not in sys.path:
        sys.path.insert(0, str(sp))

    # 3) Windows: 显式加入私有解释器 DLL 目录，避免运行时误用系统路径。
    if os.name == "nt":
        try:
            import os as _os
            dlls_dir = pyexe.parent / "DLLs"
            if dlls_dir.exists():
                _os.add_dll_directory(str(dlls_dir))
        except Exception:
            pass

def _ensure_pip(main_python: Path) -> bool:
    """
    确保专用 Python(python311/python.exe) 内 pip 可用并升级。
    不再创建/使用 venv。
    """
    import subprocess
    import urllib.request

    if not main_python.exists():
        raise RuntimeError(f"[ERR] 主 Python 不存在: {main_python}")

    # If not a real python.exe, skip pip bootstrap (prevents get-pip in app dir)
    try:
        name = main_python.name.lower()
        if not (name.startswith('python') and name.endswith('.exe')):
            print(f"[WARN] pip bootstrap skipped for non-python executable: {main_python}")
            return False
    except Exception:
        pass


    # 修复 embedded/_pth 情况
    try:
        pth_candidates = list(main_python.parent.glob("python*.pth")) + list(main_python.parent.glob("python*._pth"))
        for pth_file in pth_candidates:
            content = pth_file.read_text(encoding="utf-8")
            if "#import site" in content:
                from pathlib import Path
                Path(pth_file).write_text(content.replace("#import site", "import site"), encoding="utf-8")
    except Exception:
        pass

    # 检测 pip
    try:
        subprocess.check_call([str(main_python), "-m", "pip", "--version"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
        pip_ready_event.set()
        return True
    except Exception:
        pass

    # 安装 pip
    gp_url = "https://bootstrap.pypa.io/get-pip.py"
    gp_path = main_python.parent / "get-pip.py"
    urllib.request.urlretrieve(gp_url, gp_path)
    subprocess.check_call([str(main_python), str(gp_path)], timeout=180, creationflags=flags)

    # 升级三件套
    cmd = [str(main_python), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel", "--no-cache-dir", *PIP_INSTALL_SUPPRESS_ARGS]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=flags)
    ok = res.returncode == 0
    if ok:
        pip_ready_event.set()
    return ok

def _current_installed(pyexe):
    """获取当前环境已安装的包列表"""
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
        r = subprocess.run(["nvidia-smi"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2, creationflags=flags)
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
            errors="replace",
            timeout=2,
            creationflags=flags,
        )
    except Exception:
        return False
    output = f"{r.stdout or ''}\n{r.stderr or ''}".lower()
    return r.returncode == 0 and "cuda" in output


def _diagnose_install_failure(output: str, returncode: int) -> str:
    """
    分析 pip 安装失败的输出，诊断具体原因
    """
    output_lower = output.lower()

    if ("antlr4-python3-runtime" in output_lower) and ("bdist_wheel" in output_lower):
        return "🧩 antlr4-python3-runtime 构建环境缺少 wheel - 可先补齐 pip/setuptools/wheel 并关闭 build isolation"
    
    # 1. 文件/进程占用（最常见的权限问题）
    if any(x in output_lower for x in [
        "permission denied",
        "access is denied",
        "being used by another process",
        "permissionerror",
        "winerror 5",
        "winerror 32",  # 文件被另一进程使用
        "errno 13",
    ]):
        return "🔒 文件被占用或权限不足 - 请关闭程序后重试，或以管理员身份运行"
    
    # 2. 依赖冲突
    if any(x in output_lower for x in [
        "conflicting dependencies",
        "incompatible",
        "no matching distribution",
        "could not find a version",
        "resolutionimpossible",
        "package requires",
    ]):
        return "⚠️ 依赖版本冲突 - 某些包的版本要求互相矛盾"
    
    # 3. 网络问题
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
    
    # 4. 磁盘空间
    if any(x in output_lower for x in [
        "no space left",
        "disk full",
        "not enough space",
        "oserror: [errno 28]",
    ]):
        return "💾 磁盘空间不足 - 请清理磁盘后重试"
    
    # 5. 编译失败（C扩展）
    if any(x in output_lower for x in [
        "building wheel",
        "failed building",
        "error: command",
        "microsoft visual c++",
        "vcvarsall.bat",
        "cl.exe",
    ]):
        return "🔧 编译失败 - 可能缺少 Visual C++ Build Tools"
    
    # 6. Python 版本不兼容
    if any(x in output_lower for x in [
        "requires python",
        "python_requires",
        "not supported",
    ]):
        return "🐍 Python 版本不兼容 - 该包不支持当前 Python 版本"
    
    # 7. pip 本身的问题
    if any(x in output_lower for x in [
        "pip._internal",
        "attributeerror",
        "modulenotfounderror: no module named 'pip'",
    ]):
        return "📦 pip 损坏或版本过低 - 请先升级 pip"
    
    # 8. CUDA/GPU 相关
    if any(x in output_lower for x in [
        "cuda",
        "cudnn",
        "nvidia",
        "gpu",
    ]) and "error" in output_lower:
        return "🎮 CUDA/GPU 相关错误 - 请检查 CUDA 版本是否匹配"
    
    # 默认
    if returncode == 1:
        return f"❓ 一般错误 (code={returncode}) - 请查看上方日志获取详情"
    elif returncode == 2:
        return f"❓ 命令行语法错误 (code={returncode})"
    else:
        return f"❓ 未知错误 (code={returncode}) - 请查看上方日志获取详情"


def _run_logged_pip_command(pyexe, pip_args, stop_event, log_q, flags=0, use_mirror=False, proc_setter=None, timeout=1200):
    import subprocess
    from pathlib import Path

    proc = None
    output_lines = []
    env = os.environ.copy()
    main_site = Path(pyexe).parent / "Lib" / "site-packages"
    if main_site.exists():
        env["PYTHONPATH"] = f"{main_site};{env.get('PYTHONPATH', '')}"
    env["PYTHONUNBUFFERED"] = "1"

    args = [str(pyexe), "-m", "pip", *pip_args]
    if use_mirror:
        args += ["-i", "https://pypi.tuna.tsinghua.edu.cn/simple"]
    else:
        args += ["-i", "https://pypi.org/simple"]

    log_q.put(f"[CMD] {' '.join(args)}")
    try:
        with subprocess_lock:
            proc = safe_run(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                encoding="utf-8",
                env=env,
                creationflags=flags,
            )
        if proc_setter is not None:
            try:
                proc_setter(proc)
            except Exception:
                pass

        for line in proc.stdout:
            if stop_event.is_set():
                log_q.put("[CANCEL] 用户取消安装，正在终止当前 pip 进程...")
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                return False, "\n".join(output_lines)
            line = line.rstrip()
            log_q.put(line)
            output_lines.append(line)
        proc.communicate(timeout=timeout)
        return proc.returncode == 0, "\n".join(output_lines)
    except subprocess.TimeoutExpired:
        log_q.put("[WARN] pip 恢复命令执行超时")
        try:
            if proc is not None:
                proc.kill()
        except Exception:
            pass
        return False, "\n".join(output_lines)
    except Exception as e:
        log_q.put(f"[WARN] pip 恢复命令异常: {e}")
        return False, "\n".join(output_lines)
    finally:
        if proc_setter is not None:
            try:
                proc_setter(None)
            except Exception:
                pass


def _maybe_recover_antlr_wheel_failure(pyexe, pkg, output: str, stop_event, log_q, use_mirror=False, flags=0, proc_setter=None) -> bool:
    lower = str(output or "").lower()
    pkg_lower = re.split(r'[<>=!~ ]', str(pkg or ""), 1)[0].strip().lower()
    if pkg_lower not in {"rapidocr", "omegaconf", "antlr4-python3-runtime"}:
        return False
    if "antlr4-python3-runtime" not in lower:
        return False
    if "bdist_wheel" not in lower and "metadata-generation-failed" not in lower:
        return False

    log_q.put("[INFO] 检测到 antlr4-python3-runtime 构建失败，尝试自动修复打包工具链...")

    ok_tools, _ = _run_logged_pip_command(
        pyexe,
        ["install", "--upgrade", "pip", "setuptools", "wheel", "--no-cache-dir", *PIP_INSTALL_SUPPRESS_ARGS],
        stop_event,
        log_q,
        flags=flags,
        use_mirror=use_mirror,
        proc_setter=proc_setter,
        timeout=900,
    )
    if not ok_tools:
        log_q.put("[WARN] 自动补齐 pip/setuptools/wheel 失败，无法继续 antlr 构建恢复。")
        return False

    ok_antlr, _ = _run_logged_pip_command(
        pyexe,
        ["install", "antlr4-python3-runtime==4.9.3", "--no-build-isolation", *PIP_INSTALL_SUPPRESS_ARGS],
        stop_event,
        log_q,
        flags=flags,
        use_mirror=use_mirror,
        proc_setter=proc_setter,
        timeout=900,
    )
    if not ok_antlr:
        log_q.put("[WARN] 预装 antlr4-python3-runtime==4.9.3 失败，antlr 构建恢复未生效。")
        return False

    log_q.put("[OK] antlr4-python3-runtime 恢复已完成，准备重试当前包。")
    return True

# pip 安装入口：支持 pause_event、实时日志和镜像切换
def _pip_install(pyexe, pkg, stop_event, log_q, use_mirror=False, flags=0, pause_event=None,
                 force_reinstall=False, no_cache=False, proc_setter=None):
    """安装单个依赖包，支持实时日志、镜像切换、重试与防阻塞。"""
    import os
    import re
    import subprocess
    import time
    import traceback
    from pathlib import Path

    max_retries = 2
    retry = 0
    proc = None
    antlr_recovery_applied = False

    def _root_name(spec: str) -> str:
        return re.split(r'[<>=!~ ]', spec, 1)[0].strip().lower()
    # Fallback 修复：防止传入错误 pyexe
    if not Path(pyexe).exists():
        pyexe = Path(sys.executable)
        log_q.put(f"[WARN] 传入 Python 不存在，自动切换为 {pyexe}")

    if not pip_ready_event.wait(timeout=60):
        log_q.put(f"[ERR] pip 未初始化完成，跳过 {pkg}")
        return False

    env = os.environ.copy()
    main_site = Path(pyexe).parent / "Lib" / "site-packages"
    if main_site.exists():
        env["PYTHONPATH"] = f"{main_site};{env.get('PYTHONPATH', '')}"
    env["PYTHONUNBUFFERED"] = "1"
    name = _root_name(pkg)
    mirror_index = "https://pypi.tuna.tsinghua.edu.cn/simple"
    official_index = "https://pypi.org/simple"

    while retry <= max_retries:
        if stop_event.is_set():
            log_q.put("[INFO] 检测到停止信号，中断安装任务。")
            return False
        # 若处于暂停状态，则等待继续
        if pause_event is not None and not pause_event.is_set():
            log_q.put("[INFO] 已暂停，等待继续 ...")
            while not pause_event.is_set():

                if stop_event.is_set():
                    log_q.put("[CANCEL] 用户取消安装。")
                    return False
                time.sleep(0.1)
        try:
            args = [
                str(pyexe), "-m", "pip", "install",
                pkg, "--upgrade", *PIP_INSTALL_SUPPRESS_ARGS
            ]
            # 需要强制重装的包（版本冲突敏感）
            force_reinstall_pkgs = {
                "protobuf",
            }
            
            if force_reinstall:
                args.append("--force-reinstall")
                if no_cache:
                    args.append("--no-cache-dir")
            elif name in force_reinstall_pkgs:
                args.append("--force-reinstall")
            else:
                # 其他包：普通升级即可，不强制重装依赖
                pass
            
            # Qt 顶层包禁依赖以防触发 PyQt6-Qt6 重装
            if name in {"pyqt6", "pyqt6-webengine"}:
                args.append("--no-deps")
            if name in {"onnxruntime", "onnxruntime-gpu"}:
                args.append("--no-deps")

            if use_mirror:
                args += ["-i", mirror_index]
                if retry == 0:
                    log_q.put("[Source] 使用清华源 📦")
            else:
                args += ["-i", official_index]
                if retry == 0:
                    log_q.put("[Source] 使用官方源 🌐")

            log_q.put(f"[CMD] {' '.join(args)}")
            with subprocess_lock:
                proc = safe_run(
                    args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    encoding="utf-8",
                    env=env,
                    creationflags=flags
                )
            if proc_setter is not None:
                try:
                    proc_setter(proc)
                except Exception:
                    pass

            # 收集输出用于错误诊断
            output_lines = []
            for line in proc.stdout:
                if stop_event.is_set():
                    log_q.put("[CANCEL] 用户取消安装，正在终止当前 pip 进程...")
                    try:
                        proc.terminate()
                        proc.wait(timeout=5)
                    except Exception:
                        try:
                            proc.kill()
                        except Exception:
                            pass
                    return False
                # 运行中支持暂停/继续
                if pause_event is not None:
                    while not pause_event.is_set():
                        if stop_event.is_set():
                            try:
                                proc.terminate()
                            except Exception:
                                pass
                            return False
                        time.sleep(0.1)
                log_q.put(line.rstrip())
                output_lines.append(line.rstrip())
            proc.communicate(timeout=1200)

            if proc.returncode == 0:
                log_q.put(f"[OK] {pkg} 安装成功 ✅")
                return True
            else:
                if stop_event.is_set():
                    log_q.put("[CANCEL] 用户取消安装。")
                    return False
                # 分析失败原因
                full_output = "\n".join(output_lines[-50:])  # 最后50行
                failure_reason = _diagnose_install_failure(full_output, proc.returncode)
                
                log_q.put(f"[WARN] {pkg} 安装失败 (returncode={proc.returncode})")
                log_q.put(f"[DIAG] 可能原因: {failure_reason}")

                if not antlr_recovery_applied:
                    antlr_recovery_applied = _maybe_recover_antlr_wheel_failure(
                        pyexe,
                        pkg,
                        full_output,
                        stop_event,
                        log_q,
                        use_mirror=use_mirror,
                        flags=flags,
                        proc_setter=proc_setter,
                    )
                    if antlr_recovery_applied:
                        log_q.put("[INFO] 已应用 antlr/wheel 恢复，立即重试当前包...")
                        time.sleep(1)
                        continue
                
                retry += 1
                if retry <= max_retries:
                    log_q.put(f"[INFO] 第 {retry} 次重试中... ⏳")
                else:
                    # 所有重试都失败，提供手动安装命令
                    log_q.put(f"[ERR] {pkg} 安装失败 ❌")
                    log_q.put(f"[ERR] 失败原因: {failure_reason}")
                    log_q.put("")
                    log_q.put("=" * 60)
                    log_q.put("💡 手动安装提示（请在终端中执行以下命令）：")
                    log_q.put("")
                    manual_cmd = f'"{pyexe}" -m pip install {pkg} --upgrade --user'
                    log_q.put(f"  {manual_cmd}")
                    log_q.put("")
                    log_q.put("如遇权限问题，可尝试：")
                    log_q.put('  1. 关闭程序后以管理员身份运行终端')
                    log_q.put('  2. 或使用 --user 选项安装到用户目录')
                    log_q.put('  3. 或在设置中点击"打开环境终端"执行上述命令')
                    log_q.put("=" * 60)
                    log_q.put("")
                    return False
             # 重试前也响应暂停/取消
                if pause_event is not None:
                    while not pause_event.is_set():
                        if stop_event.is_set():
                            return False
                        time.sleep(0.1)
                time.sleep(3)
                continue

        except subprocess.TimeoutExpired:
            log_q.put(f"[ERR] {pkg} 安装超时，正在重试...")
            retry += 1
            continue
        except Exception as e:
            tb = traceback.format_exc()
            log_q.put(f"[FATAL] {pkg} 安装异常: {e}\n{tb}")
            return False
        finally:
            if proc_setter is not None:
                try:
                    proc_setter(None)
                except Exception:
                    pass

    # 检查 pip 可用
    try:
        subprocess.check_call(
            [str(pyexe), "-m", "pip", "--version"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags
        )
    except Exception:
        log_q.put(f"[ERR] pip 不可用，跳过 {pkg}")
        return False
    # 防御式返回（正常流程不会走到这里）
    return False

# --------------- UI ---------------
def _build_layers_ui(pyexe, deps_dir, installed_layers, default_select, chosen, state_path,
                     from_settings=False, skip_runtime_verify_once=False):
    # 使用外部传入的 installed_layers；不覆盖
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

    # 与主窗口保持一致：统一使用本模块的 Fluent 主题同步逻辑。
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
        # 可选：通知后台停止任务
        try:
            global stop_event
            if 'stop_event' in globals():
                stop_event.set()
        except Exception:
            pass
        # 立即退出（不弹确认）
        QTimer.singleShot(0, lambda: QApplication.instance().quit())
        QTimer.singleShot(20, lambda: sys.exit(0))

    def _on_close(evt):
        evt.accept()
        _force_quit()

    # 新增：读取已安装层
    state_file = os.path.join(deps_dir, ".deps_state.json")
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

    # ====== 运行时验证：检查声称已安装的层是否真正可用 ======
    # 新增：如果不是设置页面重启且已安装 basic 和 core，则跳过验证
    # 直接使用 from_settings 参数
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
    # ====== 验证结束 ======

    py_ready = bool(pyexe and os.path.exists(str(pyexe)))

    # 判断是否缺少关键层（BASIC / CORE / MathCraft ONNX 后端）
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

    # 获取验证失败的层名列表
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

    # 遍历所有功能层
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

    # ---------- MathCraft CPU / GPU 后端互斥逻辑 ----------
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

    # ---------- GPU 加速提示 ----------
    gpu_info_label = QLabel()
    has_nvidia_gpu = _gpu_available()
    has_cuda_toolkit = _cuda_toolkit_available()
    if has_nvidia_gpu and has_cuda_toolkit:
        gpu_info_label.setText(
            "✅ 检测到 NVIDIA GPU 和 CUDA Toolkit；可选择 MATHCRAFT_GPU 使用 onnxruntime-gpu 后端"
        )
        gpu_info_label.setStyleSheet(f"color:{theme['ok']};font-size:12px;margin:4px 0;")
    elif has_nvidia_gpu:
        gpu_info_label.setText(
            "⚠️ 检测到 NVIDIA GPU，但未检测到 nvcc/CUDA Toolkit；仍可手动选择 MATHCRAFT_GPU"
        )
        gpu_info_label.setStyleSheet(f"color:{theme['hint']};font-size:12px;margin:4px 0;")
    else:
        gpu_info_label.setText("⚠️ 未检测到 NVIDIA GPU，建议使用默认 MATHCRAFT_CPU 后端")
        gpu_info_label.setStyleSheet(f"color:{theme['hint']};font-size:12px;margin:4px 0;")
    lay.addWidget(gpu_info_label)
    # 路径显示与更改
    path_row = QHBoxLayout()
    path_edit = QLineEdit(deps_dir)
    path_edit.setReadOnly(True)
    btn_path = PushButton(FluentIcon.FOLDER, "更改依赖安装/加载路径")
    btn_path.setFixedHeight(36)
    btn_path.setToolTip("更改后需要重启程序才能生效")
    path_row.addWidget(QLabel("依赖安装/加载路径:"))
    path_row.addWidget(path_edit, 1)
    path_row.addWidget(btn_path)
    lay.addLayout(path_row)

    # 下载源选择（与主设置页保持一致的 Fluent 风格）
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

    # ---------- 按钮布局 ----------
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

    # 警告 label
    warn = QLabel("缺少关键依赖层，部分功能将不可用！")
    warn.setStyleSheet(f"color:{theme['warn']};")
    lay.addWidget(warn)

    # 说明 label
    desc = QLabel(
        "📦 层级说明：\n"
        "• BASIC：基础运行层，包含网络、图像处理和通用工具依赖。\n"
        "• CORE：识别功能层，包含 MathCraft ONNX OCR 及文档导出 / PDF 相关依赖。\n"
        "• MATHCRAFT_CPU：ONNX Runtime CPU 后端，默认推荐，稳定性更高。\n"
        "• MATHCRAFT_GPU：ONNX Runtime GPU 后端，需要本机 NVIDIA 驱动 / CUDA DLL 可用。\n"
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

    # 动态更新按钮和警告
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
        nonlocal failed_layer_names
        import os
        d = _select_existing_directory_with_icon(dlg, "选择依赖安装/加载目录", deps_dir)
        if d:
            normalized = str(_normalize_deps_base_dir(Path(d)))
            path_edit.setText(normalized)
            state_file = os.path.join(normalized, ".deps_state.json")
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
            py_ready_local = bool(_find_existing_python(Path(normalized)))
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
            # 移除与 venv/调试相关输出，避免策略混用
            update_ui()
            # 保存新路径到配置
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
                print(f"[INFO] 依赖路径已保存并刷新状态: {normalized}")
            except Exception as e:
                print(f"[ERR] 保存配置失败: {e}")

    btn_path.clicked.connect(choose_path)

    def enter():
        """进入按钮：环境完整则进入；缺关键层时按入口策略决定是否允许跳过安装。"""
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

        # 环境完整时直接进入
        if not missing:
            chosen["action"] = "enter"
            chosen["layers"] = []
            chosen["force_enter"] = False
            dlg.accept()
            return

        # 缺少关键层：允许用户在风险自担下跳过安装并进入。
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

    # ---------- UI 刷新函数 ----------
    def refresh_ui():
        """在安装完成后刷新依赖状态"""
        nonlocal failed_layer_names
        try:
            new_state = _sanitize_state_layers(Path(state_path))
            installed_layers["layers"] = new_state.get("installed_layers", [])
            failed_layer_names = new_state.get("failed_layers", [])

            # 更新警告与按钮文本
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

            # 更新复选框
            effective_default_select = _effective_default_select()
            for layer, cb in checks.items():
                _sync_layer_checkbox(layer, cb, delete_buttons[layer], effective_default_select)

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

    # ✅ 暴露给外部调用
    dlg.refresh_ui = refresh_ui

    # ---------- 退出按钮逻辑：直接退出程序 ----------
    _closing_dialog = {"active": False}

    def _exit_app():
        """退出按钮：先确认，然后直接退出程序"""
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

    # 右上角关闭事件：与退出按钮一致
    def _on_close(evt):
        if _closing_dialog["active"]:
            evt.accept()
            return
        _exit_app()
        evt.ignore()  # 由 _exit_app 控制退出
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
    progress.setFixedHeight(20)  # 增加高度
    progress.setMinimumWidth(400)  # 增加宽度

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
        # 与主 Fluent 主题对齐：不手工覆盖整窗和文本框背景。
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
    try:
        from PyQt6.QtGui import QIcon
        icon_path = resource_path("assets/icon.ico")
        if icon_path and os.path.exists(icon_path):
            win.setWindowIcon(QIcon(icon_path))
    except Exception:
        pass


def _select_existing_directory_with_icon(parent, title: str, initial_dir: str) -> str:
    from PyQt6.QtWidgets import QFileDialog
    dlg = QFileDialog(parent, title, initial_dir)
    dlg.setFileMode(QFileDialog.FileMode.Directory)
    dlg.setOption(QFileDialog.Option.ShowDirsOnly, True)
    _apply_app_window_icon(dlg)
    if dlg.exec() != QFileDialog.DialogCode.Accepted:
        return ""
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
    """
    清空依赖状态文件，用于当依赖目录损坏或首次初始化异常时自动修复。
    """
    import json
    import os
    from pathlib import Path

    try:
        # 确定配置文件路径
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

        # 删除状态文件
        state_path = Path(deps_dir) / ".deps_state.json"
        if state_path.exists():
            state_path.unlink()
            print(f"[OK] 已删除状态文件：{state_path}")

        # 重建空状态文件
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
    """Locate the bundled/local Python 3.11 installer without downloading anything."""
    candidates: list[Path] = []
    try:
        candidates.append(deps_dir / "python-3.11.0-amd64.exe")
    except Exception:
        pass
    try:
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            candidates.append(Path(sys._MEIPASS) / "python-3.11.0-amd64.exe")
    except Exception:
        pass
    try:
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "_internal" / "python-3.11.0-amd64.exe")
        candidates.append(exe_dir / "python-3.11.0-amd64.exe")
    except Exception:
        pass
    candidates.extend([
        Path(__file__).resolve().parent.parent / "python-3.11.0-amd64.exe",
        Path.cwd() / "python-3.11.0-amd64.exe",
    ])
    seen: set[str] = set()
    for candidate in candidates:
        try:
            key = str(candidate.resolve()).lower()
        except Exception:
            key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            if candidate.exists():
                return candidate
        except Exception:
            continue
    return None


def _iter_python_candidates(base_dir: Path) -> list[Path]:
    """Return likely python.exe candidates inside the selected dependency directory."""
    base_dir = Path(base_dir)
    candidates = [
        base_dir / "python.exe",
        base_dir / "Scripts" / "python.exe",
        base_dir / "python311" / "python.exe",
        base_dir / "python311" / "Scripts" / "python.exe",
        base_dir / "Python311" / "python.exe",
        base_dir / "Python311" / "Scripts" / "python.exe",
        base_dir / "python_full" / "python.exe",
        base_dir / "venv" / "Scripts" / "python.exe",
        base_dir / ".venv" / "Scripts" / "python.exe",
    ]
    try:
        for child in base_dir.iterdir():
            if not child.is_dir():
                continue
            name = child.name.lower()
            if name in {"venv", ".venv", "python_full"} or name.startswith("python"):
                candidates.extend([
                    child / "python.exe",
                    child / "Scripts" / "python.exe",
                ])
    except Exception:
        pass

    seen: set[str] = set()
    ordered: list[Path] = []
    for candidate in candidates:
        try:
            key = str(candidate.resolve()).lower()
        except Exception:
            key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(candidate)
    return ordered


def _find_existing_python(base_dir: Path) -> Path | None:
    """Reuse any existing python.exe inside the selected dependency directory."""
    for candidate in _iter_python_candidates(base_dir):
        try:
            if candidate.exists():
                return candidate
        except Exception:
            continue
    return None


def _normalize_deps_base_dir(selected_dir: Path) -> Path:
    """
    Normalize the dependency base directory chosen by the user.

    The wizard manages a base directory that may contain a nested `python311`.
    If the user directly picks an empty leaf directory named like `python311`,
    treat its parent as the real base directory to avoid creating `python311/python311`.
    """
    path = Path(selected_dir)
    try:
        name = path.name.lower()
    except Exception:
        return path

    looks_like_python_leaf = (
        name in {"venv", ".venv", "python_full"}
        or name.startswith("python")
    )
    if not looks_like_python_leaf:
        return path

    existing_py = _find_existing_python(path)
    if existing_py is not None:
        return path

    parent = path.parent
    try:
        if parent and str(parent) != str(path):
            return parent
    except Exception:
        pass
    return path


def _run_local_python311_installer(installer: Path, target_dir: Path, timeout: int = 900,
                                   before_launch=None) -> bool:
    """
    Launch the local Python installer and wait for it to finish.
    The installer UI is shown to the user; no network download is attempted here.
    """
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
    return (target_dir / "python.exe").exists()

# --------------- 主入口 ---------------
def ensure_deps(prompt_ui=True, require_layers=("BASIC", "CORE"), force_enter=False, always_show_ui=False,
                deps_dir=None, from_settings=False, before_show_ui=None,
                after_force_enter=None):
    global _LAST_ENSURE_DEPS_FORCE_ENTER
    _LAST_ENSURE_DEPS_FORCE_ENTER = False
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        print("[WARN] ensure_deps 需要 GUI，但当前未创建 QApplication。请在主程序创建 QApplication 后再调用。")
        return False

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

    # 2) 先读配置，再决定是否弹目录选择框
    cfg_path = _load_config_path()
    if not deps_dir:
        deps_dir = _read_config_install_dir(cfg_path)

    if not deps_dir:
        parent = app.activeWindow()  # 没有也可为 None
        _notify_before_show_ui()
        chosen = _select_existing_directory_with_icon(parent, "选择依赖安装/加载目录", str(Path.home()))
        if not chosen:
            # 用户取消，安全返回，避免后续对 None/省略号做路径拼接
            return False
        deps_dir = str(_normalize_deps_base_dir(Path(chosen)))
        _write_config_install_dir(cfg_path, deps_dir)

    deps_path = _normalize_deps_base_dir(Path(deps_dir))
    deps_dir = str(deps_path)
    deps_path.mkdir(parents=True, exist_ok=True)

    # 重复的目录选择与保存逻辑移除（前面已处理）
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
    if is_frozen:
        # Packaged: runtime stays bundled, but dependency wizard should only treat
        # a python inside deps_dir as reusable. Missing deps python must remain
        # visible to the UI so the user can initialize it from the wizard.
        py_root = Path(deps_dir) / "python311"
        existing_pyexe = _find_existing_python(Path(deps_dir))
        pyexe = existing_pyexe or (py_root / "python.exe")
        if existing_pyexe and existing_pyexe.exists():
            print(f"[INFO] packaged: use deps python for pip: {pyexe}")
            use_bundled_python = False
        else:
            print(f"[INFO] packaged: no reusable deps python yet, wizard will initialize: {pyexe}")
            use_bundled_python = True
    else:
        # 开发模式：支持依赖隔离和私有解释器
        py_root = Path(deps_dir) / "python311"
        existing_pyexe = _find_existing_python(Path(deps_dir))
        pyexe = existing_pyexe or (py_root / "python.exe")
        deps_dir_resolved = str(Path(deps_dir).resolve())
        mismatch_reason = ""
        
        # 检查是否打包模式
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
        # 开发模式下若缺少私有 Python，只认本地安装器，不再联网下载。
        if use_bundled_python and not pyexe.exists():
            if from_settings:
                print("[INFO] 设置入口：目标依赖目录未检测到可复用 Python，先打开依赖向导，待用户确认后再初始化。")
            else:
                try:
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
                    if not ok or not pyexe.exists():
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

    # 初始化 pip（无 venv）
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
        # 只有在非 BOOTSTRAPPED 模式下才注入私有路径，避免混合不同 Python 版本的包
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
        """
        从设置页进入依赖向导时，
        在“直接进入/跳过下载”前复验已安装层。
        返回是否满足 required layers。
        """
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
            pyexe = existing_pyexe or (py_root / "python.exe")
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
                pyexe = py_root / "python.exe"
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
            # 默认选中的依赖层（首次启动时）
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
                # 用户在依赖选择窗口点“退出程序”
                return False

            chosen_layers = _normalize_chosen_layers(chosen.get("layers", []))
            mirror_source = str(chosen.get("mirror_source", "")).strip().lower()
            if mirror_source in ("off", "tuna"):
                use_mirror = (mirror_source == "tuna")
            else:
                use_mirror = bool(chosen.get("mirror", False))
                mirror_source = "tuna" if use_mirror else "off"
            missing_layers, use_bundled_python = _switch_deps_context(chosen.get("deps_path", deps_dir))

            # 检查是否跳过安装并进入（缺少关键层但用户选择直接进入）
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
                if use_bundled_python and not os.path.exists(str(pyexe)):
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
                    if not ok or not os.path.exists(str(pyexe)):
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

                # === 创建 InstallWorker ===
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
                # === 绑定信号 ===
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

                    _append_log("\n[OK] Dependencies installed ✅")
                    _append_log("[INFO] Verifying installed layers in background...")
                    _set_info_text("Dependencies downloaded, validating in background...")

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

                # === UI线程日志轮询（防阻塞/防信号风暴）===
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
                        worker.wait(5000)  # 等待最长 5 秒
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

                if result == RESULT_BACK_TO_WIZARD:
                    try:
                        state = _sanitize_state_layers(state_path)
                        installed["layers"] = state.get("installed_layers", [])
                        missing_layers = _missing_required_layers(installed["layers"])
                    except Exception:
                        pass
                    skip_next_ui_runtime_verify = bool(post_install_verify_passed.get("value", False))
                    always_show_ui = True
                    continue
                if result != QDialog.DialogCode.Accepted:
                    # 用户在进度窗口点“退出下载”，回到依赖选择窗口
                    continue
        break
    return True
