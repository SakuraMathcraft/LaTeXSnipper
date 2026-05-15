import json
import os
import subprocess
import time
from pathlib import Path

from ui.settings_dialog_helpers import (
    _existing_non_launcher_pyexe_from_env,
    _hidden_subprocess_kwargs,
    _mathcraft_code_roots,
)


class SettingsMathCraftMixin:

    def _warm_probe_cache_async(self):
        def worker():
            # MathCraft v1 uses ONNX Runtime providers; keep this probe lightweight.
            try:
                self._schedule_compute_mode_probe(force=True)
            except Exception:
                pass
        import threading
        threading.Thread(target=worker, daemon=True).start()

    def _probe_module_installed(self, pyexe: str, module: str) -> bool:
        import subprocess
        if not pyexe or not os.path.exists(pyexe):
            return False
        roots = _mathcraft_code_roots()
        code = (
            "import importlib.util, sys; "
            f"[sys.path.insert(0, p) for p in reversed({roots!r}) if p not in sys.path]; "
            f"sys.exit(0 if importlib.util.find_spec({module!r}) else 1)"
        )
        try:
            try:
                res = subprocess.run(
                    [pyexe, "-c", code],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    **_hidden_subprocess_kwargs(),
                )
            except subprocess.TimeoutExpired:
                return False
            return res.returncode == 0
        except Exception:
            return False

    def _schedule_mathcraft_pkg_probe(self):
        pyexe = self.mathcraft_pyexe_input.text().strip()
        if not pyexe or not os.path.exists(pyexe):
            self._mathcraft_pkg_ready = False
            self._update_mathcraft_visibility()
            return
        def worker():
            ok = self._probe_module_installed(pyexe, "mathcraft_ocr")
            try:
                self.mathcraft_pkg_probe_done.emit(bool(ok))
            except Exception:
                pass
        import threading
        threading.Thread(target=worker, daemon=True).start()

    def _set_mathcraft_pkg_ready(self, ready: bool):
        self._mathcraft_pkg_ready = bool(ready)
        self._update_mathcraft_visibility()

    def _infer_compute_mode_from_env(self, pyexe: str) -> dict:
        try:
            env_root = self._python_env_root(pyexe)
            site = env_root / "Lib" / "site-packages"
            if not site.exists():
                return {}
            names = {d.name.lower() for d in site.iterdir()}
            has_ort = any(name.startswith("onnxruntime-") for name in names) or (site / "onnxruntime").exists()
            if not has_ort:
                return {}
            has_gpu_runtime = any(name.startswith("onnxruntime_gpu-") or name.startswith("onnxruntime-gpu-") for name in names)
            info = {
                "present": True,
                "providers": [],
                "gpu_name": "",
                "cpu_name": "",
                "gpu_available": False,
            }
            if has_gpu_runtime:
                info["providers"] = ["CUDAExecutionProvider"]
                info["gpu_available"] = True
            else:
                info["providers"] = ["CPUExecutionProvider"]
            return info
        except Exception:
            return {}

    def _probe_compute_mode_info(self, pyexe: str) -> dict:
        if not pyexe or not os.path.exists(pyexe):
            return {"present": False, "error": "python.exe not found"}
        code = (
            "import json\n"
            "out={'present': False, 'providers': [], 'gpu_available': False, 'gpu_name': '', 'cpu_name': ''}\n"
            "try:\n"
            " import onnxruntime as ort\n"
            " providers = list(ort.get_available_providers() or [])\n"
            " out['present'] = True\n"
            " out['providers'] = providers\n"
            " out['gpu_available'] = any(p in providers for p in ('CUDAExecutionProvider', 'TensorrtExecutionProvider', 'DmlExecutionProvider'))\n"
            "except Exception as e:\n"
            " out['error'] = f'{e.__class__.__name__}: {e}'\n"
            "print(json.dumps(out, ensure_ascii=False))\n"
        )
        try:
            res = subprocess.run(
                [pyexe, "-c", code],
                capture_output=True,
                text=True,
                timeout=6,
                **_hidden_subprocess_kwargs(),
            )
            raw = (res.stdout or "").strip()
            if raw:
                try:
                    info = json.loads(raw.splitlines()[-1])
                    if isinstance(info, dict):
                        gpu_name, cpu_name = self._probe_local_device_names()
                        if gpu_name and not info.get("gpu_name"):
                            info["gpu_name"] = gpu_name
                        if cpu_name and not info.get("cpu_name"):
                            info["cpu_name"] = cpu_name
                        return info
                except Exception:
                    pass
            env_info = self._infer_compute_mode_from_env(pyexe)
            if env_info:
                gpu_name, cpu_name = self._probe_local_device_names()
                if gpu_name and not env_info.get("gpu_name"):
                    env_info["gpu_name"] = gpu_name
                if cpu_name and not env_info.get("cpu_name"):
                    env_info["cpu_name"] = cpu_name
                return env_info
            return {"present": False, "error": (res.stderr or raw or "probe failed").strip()}
        except Exception as e:
            env_info = self._infer_compute_mode_from_env(pyexe)
            if env_info:
                gpu_name, cpu_name = self._probe_local_device_names()
                if gpu_name and not env_info.get("gpu_name"):
                    env_info["gpu_name"] = gpu_name
                if cpu_name and not env_info.get("cpu_name"):
                    env_info["cpu_name"] = cpu_name
                return env_info
            return {"present": False, "error": str(e)}

    def _probe_local_device_names(self) -> tuple[str, str]:
        now = time.monotonic()
        cached = getattr(self, "_device_name_cache", {}) or {}
        ttl = 300.0
        if (now - float(cached.get("ts", 0.0) or 0.0)) <= ttl:
            return str(cached.get("gpu", "") or ""), str(cached.get("cpu", "") or "")

        def _run_ps(cmd: str) -> str:
            try:
                res = subprocess.run(
                    ["powershell", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    **_hidden_subprocess_kwargs(),
                )
                lines = [line.strip() for line in (res.stdout or "").splitlines() if line.strip()]
                return lines[0] if lines else ""
            except Exception:
                return ""

        gpu_name = _run_ps("(Get-WmiObject Win32_VideoController | Where-Object {$_.Name -and $_.Name -notmatch 'Microsoft Basic'} | Select-Object -First 1 -ExpandProperty Name)")
        if not gpu_name:
            gpu_name = _run_ps("(Get-CimInstance Win32_VideoController | Where-Object {$_.Name -and $_.Name -notmatch 'Microsoft Basic'} | Select-Object -First 1 -ExpandProperty Name)")
        if not gpu_name:
            try:
                res = subprocess.run(
                    ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    **_hidden_subprocess_kwargs(),
                )
                names = [line.strip() for line in (res.stdout or "").splitlines() if line.strip()]
                gpu_name = names[0] if names else ""
            except Exception:
                gpu_name = ""

        cpu_name = _run_ps("(Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty Name)")
        if not cpu_name:
            cpu_name = _run_ps("(Get-WmiObject Win32_Processor | Select-Object -First 1 -ExpandProperty Name)")

        self._device_name_cache = {"gpu": gpu_name, "cpu": cpu_name, "ts": now}
        return gpu_name, cpu_name

    def _refresh_env_status(self, env_key: str):
        if env_key != "mathcraft":
            return
        self._schedule_compute_mode_probe(force=True)
        self._schedule_mathcraft_pkg_probe()

    def _current_mathcraft_pyexe(self) -> str:
        try:
            return self.mathcraft_pyexe_input.text().strip()
        except Exception:
            return ""

    def _init_model_combo(self):
        # Initialize the model combo-box selection.
        current = "mathcraft"
        if self.parent() and hasattr(self.parent(), "desired_model"):
            current = self.parent().desired_model
        elif self.parent() and hasattr(self.parent(), "cfg"):
            current = self.parent().cfg.get("desired_model", current)
        if not current and self.parent() and hasattr(self.parent(), "current_model"):
            current = self.parent().current_model
        if current and str(current).startswith("mathcraft"):
            current_key = "mathcraft"
        else:
            current_key = current
        for i, (key, _) in enumerate(self._model_options):
            if key == current_key:
                self.model_combo.setCurrentIndex(i)
                break
        self._init_mathcraft_pyexe()
        self._schedule_mathcraft_pkg_probe()
        self._init_mathcraft_mode()
        self._init_external_model_config()
        self._update_mathcraft_visibility()

    def _on_model_combo_changed(self, index: int):
        # Model combo-box selection changed.
        if getattr(self, "_model_selection_syncing", False):
            return
        if index < 0 or index >= len(self._model_options):
            return
        key, _ = self._model_options[index]
        if key == "external_model":
            self.select_model("external_model")
        elif self._is_mathcraft_ready():
            mode_key = self._get_mathcraft_mode_key()
            self.select_model(self._mathcraft_mode_to_model(mode_key))
        else:
            # Trigger loading or hints while keeping the UI selection on mathcraft.
            self.select_model("mathcraft")
        self._update_model_desc()
        self._update_mathcraft_visibility()

    def _init_mathcraft_pyexe(self):
        pyexe = self._resolve_dynamic_main_pyexe()
        self.mathcraft_pyexe_input.setText(pyexe)
        cfg = self._settings_cfg()
        if cfg:
            cfg.set("mathcraft_pyexe", pyexe)

    def _init_mathcraft_mode(self):
        mode = "formula"
        if self.parent() and hasattr(self.parent(), "cfg"):
            mode = self.parent().cfg.get("mathcraft_mode", "formula")
        if mode not in {"formula", "mixed", "text"}:
            mode = "formula"
        for i in range(self.mathcraft_mode_combo.count()):
            if self.mathcraft_mode_combo.itemData(i) == mode:
                prev = self.mathcraft_mode_combo.blockSignals(True)
                self.mathcraft_mode_combo.setCurrentIndex(i)
                self.mathcraft_mode_combo.blockSignals(prev)
                break

    def _mathcraft_mode_to_model(self, mode_key: str) -> str:
        mapping = {
            "formula": "mathcraft",
            "mixed": "mathcraft_mixed",
            "text": "mathcraft_text",
        }
        return mapping.get(mode_key, "mathcraft")

    def _get_mathcraft_mode_key(self) -> str:
        idx = self.mathcraft_mode_combo.currentIndex()
        if idx >= 0:
            key = self.mathcraft_mode_combo.itemData(idx)
            if key:
                return key
        return "formula"

    def _settings_cfg(self):
        if self.parent() and hasattr(self.parent(), "cfg"):
            return self.parent().cfg
        return None

    @staticmethod
    def _normalize_install_base_dir(selected_dir: Path) -> Path:
        path = Path(selected_dir).expanduser()
        try:
            path = path.resolve()
        except Exception:
            path = path.absolute()
        if not path.exists() or not path.is_dir():
            return path
        leaf = path.name.lower()
        if not (leaf.startswith("python") or leaf in {"venv", ".venv", "scripts", "python_full"}):
            return path
        existing_py = SettingsMathCraftMixin._find_install_base_python(path)
        if existing_py is not None:
            return path
        return path.parent if path.parent != path else path

    @staticmethod
    def _find_install_base_python(base_dir: Path) -> Path | None:
        try:
            from bootstrap.deps_python_runtime import find_existing_python

            return find_existing_python(Path(base_dir))
        except Exception:
            return None

    @staticmethod
    def _python_env_root(pyexe: str | Path) -> Path:
        p = Path(pyexe)
        return p.parent.parent if p.parent.name.lower() in {"scripts", "bin"} else p.parent

    def _current_install_base_dir(self) -> Path | None:
        cfg = self._settings_cfg()
        raw = ""
        try:
            if cfg:
                raw = cfg.get("install_base_dir", "") or ""
        except Exception:
            raw = ""
        if not raw:
            raw = os.environ.get("LATEXSNIPPER_INSTALL_BASE_DIR", "") or ""
        raw = str(raw).strip()
        if not raw:
            return None
        try:
            return self._normalize_install_base_dir(Path(raw))
        except Exception:
            return None

    def _resolve_dynamic_main_pyexe(self) -> str:
        env_pyexe = _existing_non_launcher_pyexe_from_env()
        if env_pyexe:
            return env_pyexe

        base_dir = self._current_install_base_dir()
        if base_dir is not None:
            candidate = self._find_install_base_python(base_dir)
            if candidate is not None:
                return str(candidate)
            return ""
        return ""

    def _is_mathcraft_selected(self) -> bool:
        idx = self.model_combo.currentIndex()
        if idx >= 0 and idx < len(self._model_options):
            key, _ = self._model_options[idx]
            return key == "mathcraft"
        return False

    def _is_external_model_selected(self) -> bool:
        idx = self.model_combo.currentIndex()
        if idx >= 0 and idx < len(self._model_options):
            key, _ = self._model_options[idx]
            return key == "external_model"
        return False

    def _is_mathcraft_ready(self) -> bool:
        # only mark ready after MathCraft package is available
        if getattr(self, "_mathcraft_pkg_ready", False):
            return True
        return False

    def _on_mathcraft_mode_changed(self, index: int):
        if index < 0:
            return
        mode_key = self.mathcraft_mode_combo.itemData(index)
        if self.parent() and hasattr(self.parent(), "cfg"):
            self.parent().cfg.set("mathcraft_mode", mode_key)
        if not self._is_mathcraft_selected():
            return
        if self._is_mathcraft_ready():
            self.select_model(self._mathcraft_mode_to_model(mode_key))

    def _update_mathcraft_visibility(self):
        key = None
        idx = self.model_combo.currentIndex()
        if idx >= 0 and idx < len(self._model_options):
            key, _ = self._model_options[idx]
        visible = (key == "mathcraft")
        external_visible = (key == "external_model")
        ready = self._is_mathcraft_ready()
        pyexe = self.mathcraft_pyexe_input.text().strip()
        pyexe_exists = bool(pyexe and Path(pyexe).exists())
        try:
            self.mathcraft_env_widget.setVisible(visible)
            self.mathcraft_env_hint.setVisible(visible)
            if self.mathcraft_dl_widget is not None:
                self.mathcraft_dl_widget.setVisible(visible)
            # Keep recognition type visible so users can preselect it.
            self.mathcraft_mode_widget.setVisible(visible)
            self.external_model_widget.setVisible(external_visible)
            if visible:
                if not pyexe_exists:
                    self.mathcraft_env_hint.setText("⚠️ 主依赖环境未就绪，请先运行依赖向导。")
                elif not ready:
                    self.mathcraft_env_hint.setText("⚠️ MathCraft 未部署：请检查程序文件或依赖环境。")
                else:
                    self.mathcraft_env_hint.setText("💡 MathCraft 已就绪，可选择识别类型。")
            if external_visible:
                self._update_external_model_status()
        except Exception:
            pass

    def select_model(self, model_name: str):
        # Only emit the signal; the connected on_model_changed handler processes it.
        self.model_changed.emit(model_name)
        self._update_compute_mode_label()

    def _set_compute_mode_text(self, text: str, state: str) -> None:
        self.lbl_compute_mode.setText(text)
        self._compute_mode_state = state
        self.apply_theme_styles(force=True)

    def _set_compute_mode_detecting(self, info: dict, pyexe: str) -> None:
        if not pyexe or not os.path.exists(pyexe):
            self._set_compute_mode_text("⚪ 计算模式检测中...", "unknown")
            return
        providers = [str(p or "").strip() for p in (info.get("providers") or [])]
        gpu_available = any(
            p in ("CUDAExecutionProvider", "TensorrtExecutionProvider", "DmlExecutionProvider")
            for p in providers
        )
        if gpu_available:
            self._set_compute_mode_text("🟢 GPU 模式（检测中...）", "gpu")
        elif info.get("present"):
            self._set_compute_mode_text("🟡 CPU 模式（检测中...）", "cpu")
        else:
            self._set_compute_mode_text("⚪ 计算模式检测中...", "unknown")

    def _apply_compute_mode_from_info(self, info: dict, pyexe: str) -> bool:
        if not pyexe or not os.path.exists(pyexe):
            self._set_compute_mode_text("⚪ 计算模式未知", "unknown")
            return True
        if not isinstance(info, dict) or not info:
            return False
        if not info.get("present"):
            self._set_compute_mode_text("⚪ 计算模式未知", "unknown")
            return True
        providers = [str(p or "").strip() for p in (info.get("providers") or [])]
        gpu_available = any(
            p in ("CUDAExecutionProvider", "TensorrtExecutionProvider", "DmlExecutionProvider")
            for p in providers
        )
        gpu_name = str(info.get("gpu_name") or "").strip()
        cpu_name = str(info.get("cpu_name") or "").strip()
        if gpu_available:
            if gpu_name:
                self._set_compute_mode_text(f"🟢 GPU 可用: {gpu_name}", "gpu")
            else:
                self._set_compute_mode_text("🟢 GPU 模式", "gpu")
            return True
        if cpu_name:
            self._set_compute_mode_text(f"🟡 CPU 模式: {cpu_name}", "cpu")
        else:
            self._set_compute_mode_text("🟡 CPU 模式", "cpu")
        return True

    def _on_compute_mode_probe_done(self, info: object, pyexe: str) -> None:
        self._compute_mode_probe_running = False
        self._compute_mode_probe_py = str(pyexe or "")
        self._compute_mode_probe_ts = time.monotonic()
        self._compute_mode_probe_info = dict(info) if isinstance(info, dict) else {}
        self._apply_compute_mode_from_info(self._compute_mode_probe_info or {}, self._compute_mode_probe_py)

    def _schedule_compute_mode_probe(self, force: bool = False) -> None:
        pyexe = self._resolve_dynamic_main_pyexe()
        if not pyexe or not os.path.exists(pyexe):
            self._set_compute_mode_text("⚪ 计算模式未知", "unknown")
            return

        now = time.monotonic()
        ttl = float(getattr(self, "_probe_cache_ttl_sec", 45.0) or 45.0)
        cached_info = getattr(self, "_compute_mode_probe_info", None)
        cached_py = str(getattr(self, "_compute_mode_probe_py", "") or "")
        cached_ts = float(getattr(self, "_compute_mode_probe_ts", 0.0) or 0.0)
        if (not force) and cached_py == pyexe and isinstance(cached_info, dict) and (now - cached_ts) <= ttl:
            self._apply_compute_mode_from_info(cached_info, pyexe)
            return

        inferred = self._infer_compute_mode_from_env(pyexe)
        if self._apply_compute_mode_from_info(inferred, pyexe):
            if isinstance(inferred, dict) and inferred.get("present"):
                self._compute_mode_probe_py = pyexe
                self._compute_mode_probe_ts = now
                self._compute_mode_probe_info = dict(inferred)
        else:
            self._set_compute_mode_text("⚪ 计算模式检测中...", "unknown")

        if self._compute_mode_probe_running and not force:
            return

        if isinstance(inferred, dict) and inferred.get("present"):
            self._set_compute_mode_detecting(inferred, pyexe)
        else:
            self._set_compute_mode_text("⚪ 计算模式检测中...", "unknown")

        self._compute_mode_probe_running = True

        def worker():
            info = self._probe_compute_mode_info(pyexe)
            try:
                self.compute_mode_probe_done.emit(info, pyexe)
            except Exception:
                pass

        import threading
        threading.Thread(target=worker, daemon=True).start()

    def _update_compute_mode_label(self):
        """Update the compute-mode status label, preferring cache and probing in the background."""
        self._schedule_compute_mode_probe()

    def update_model_selection(self):
        # sync model combo selection state
        if getattr(self, "_model_selection_syncing", False):
            return
        current = "mathcraft"
        try:
            if self.parent() and hasattr(self.parent(), "desired_model"):
                current = str(self.parent().desired_model or "mathcraft")
            elif self.parent() and hasattr(self.parent(), "cfg"):
                current = str(self.parent().cfg.get("desired_model", current) or current)
        except Exception:
            current = "mathcraft"
        target = "external_model" if current == "external_model" else "mathcraft"
        self._model_selection_syncing = True
        try:
            for i, (key, _) in enumerate(self._model_options):
                if key == target:
                    self.model_combo.blockSignals(True)
                    self.model_combo.setCurrentIndex(i)
                    self.model_combo.blockSignals(False)
                    break
            self._init_mathcraft_mode()
            self._init_external_model_config()
            self._update_model_desc()
            self._update_mathcraft_visibility()
        finally:
            self._model_selection_syncing = False
