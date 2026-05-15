import json
import os
import re
import subprocess
import time
import traceback
from pathlib import Path

from backend.cuda_runtime_policy import onnxruntime_cpu_spec, onnxruntime_gpu_spec
from bootstrap.deps_context import flags
from bootstrap.deps_layer_specs import (
    LAYER_MAP,
    _normalize_chosen_layers,
    _reorder_mathcraft_install_specs,
    _version_satisfies_spec,
)
from bootstrap.deps_pandoc import _cleanup_pandoc_leftovers, _ensure_pandoc_binary, _pandoc_data_dir
from bootstrap.deps_qt_compat import QThread, pyqtSignal
from bootstrap.deps_runtime_verify import (
    _cleanup_orphan_onnxruntime_namespace,
    _cleanup_pip_interrupted_leftovers,
    _current_installed,
    _fix_critical_versions,
    _layer_verify_failure_diagnostics,
    _pip_install,
    _repair_gpu_onnxruntime_runtime,
    _uninstall_package_if_present,
    _verify_layer_runtime,
    _verify_onnxruntime_runtime,
)
from bootstrap.deps_state import load_json as _load_json, save_json as _save_json


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
