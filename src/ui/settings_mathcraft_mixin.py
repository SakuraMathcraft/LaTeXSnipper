import json
import os
import subprocess
import sys
import time
from pathlib import Path

from bootstrap.deps_python_runtime import find_existing_python
from runtime.dependency_python import clean_path_value, normalize_deps_base_dir
from ui.settings_dialog_helpers import (
    _existing_non_launcher_pyexe_from_env,
    _hidden_subprocess_kwargs,
    _mathcraft_code_roots,
)


class SettingsMathCraftMixin:
    def _probe_compute_mode_info(self, pyexe: str) -> dict:
        if not pyexe or not os.path.exists(pyexe):
            return {"present": False, "error": "Python executable not found"}
        roots = _mathcraft_code_roots()
        preference = self._current_mathcraft_provider_preference()
        code = (
            "import json, sys\n"
            f"[sys.path.insert(0, p) for p in reversed({roots!r}) if p not in sys.path]\n"
            "out={'present': False, 'active_provider': '', 'device': '', 'gpu_name': '', 'cpu_name': ''}\n"
            "try:\n"
            " from mathcraft_ocr.providers import detect_providers\n"
            f" info = detect_providers({preference!r})\n"
            " out['present'] = True\n"
            " out['active_provider'] = info.active_provider or ''\n"
            " out['device'] = info.device\n"
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
                        gpu_name, cpu_name = self._probe_local_device_names(
                            str(info.get("active_provider") or "")
                        )
                        if gpu_name and not info.get("gpu_name"):
                            info["gpu_name"] = gpu_name
                        if cpu_name and not info.get("cpu_name"):
                            info["cpu_name"] = cpu_name
                        return info
                except Exception:
                    pass
            return {"present": False, "error": (res.stderr or raw or "probe failed").strip()}
        except Exception as e:
            return {"present": False, "error": str(e)}

    def _current_mathcraft_provider_preference(self) -> str:
        try:
            model = getattr(self.parent(), "model", None)
            preference = str(getattr(model, "_provider", "") or "").strip().lower()
            if preference in {"auto", "cpu", "gpu"}:
                return preference
        except Exception:
            pass
        return "auto"

    def _probe_local_device_names(self, active_provider: str = "") -> tuple[str, str]:
        if sys.platform == "darwin":
            self._device_name_cache = {"gpu": "", "cpu": "", "ts": time.monotonic()}
            return "", ""

        now = time.monotonic()
        cached = getattr(self, "_device_name_cache", {}) or {}
        ttl = 300.0
        if (
            str(cached.get("provider", "") or "") == active_provider
            and (now - float(cached.get("ts", 0.0) or 0.0)) <= ttl
        ):
            return str(cached.get("gpu", "") or ""), str(cached.get("cpu", "") or "")

        def _first_line(args: list[str], *, timeout: float = 5.0) -> str:
            try:
                res = subprocess.run(
                    args,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout,
                    **_hidden_subprocess_kwargs(),
                )
                lines = [line.strip() for line in (res.stdout or "").splitlines() if line.strip()]
                return lines[0] if lines else ""
            except Exception:
                return ""

        def _nvidia_gpu_name() -> str:
            return _first_line(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                timeout=3,
            )

        def _windows_device_names() -> tuple[str, str]:
            def _run_ps(cmd: str) -> str:
                return _first_line(
                    ["powershell", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                    timeout=5,
                )

            gpu = ""
            if active_provider in {"CUDAExecutionProvider", "TensorrtExecutionProvider"}:
                gpu = _nvidia_gpu_name()
            if active_provider == "DmlExecutionProvider" and not gpu:
                gpu = _run_ps("(Get-CimInstance Win32_VideoController | Where-Object {$_.Name -and $_.Name -notmatch 'Microsoft Basic'} | Sort-Object AdapterRAM -Descending | Select-Object -First 1 -ExpandProperty Name)")
            if active_provider == "DmlExecutionProvider" and not gpu:
                gpu = _run_ps("(Get-WmiObject Win32_VideoController | Where-Object {$_.Name -and $_.Name -notmatch 'Microsoft Basic'} | Sort-Object AdapterRAM -Descending | Select-Object -First 1 -ExpandProperty Name)")

            cpu = _run_ps("(Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty Name)")
            if not cpu:
                cpu = _run_ps("(Get-WmiObject Win32_Processor | Select-Object -First 1 -ExpandProperty Name)")
            return gpu, cpu

        def _macos_device_names() -> tuple[str, str]:
            cpu = _first_line(["sysctl", "-n", "machdep.cpu.brand_string"], timeout=3)
            gpu = ""
            try:
                res = subprocess.run(
                    ["system_profiler", "SPDisplaysDataType"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=6,
                )
                for raw in (res.stdout or "").splitlines():
                    line = raw.strip()
                    if line.startswith("Chipset Model:"):
                        gpu = line.split(":", 1)[1].strip()
                        break
            except Exception:
                gpu = ""
            if not gpu:
                gpu = _nvidia_gpu_name()
            return gpu, cpu

        def _linux_cpu_name() -> str:
            try:
                res = subprocess.run(
                    ["lscpu"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=3,
                )
                for raw in (res.stdout or "").splitlines():
                    if raw.lower().startswith("model name:"):
                        return raw.split(":", 1)[1].strip()
            except Exception:
                pass
            try:
                for raw in Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="ignore").splitlines():
                    if raw.lower().startswith("model name"):
                        return raw.split(":", 1)[1].strip()
            except Exception:
                pass
            return ""

        def _linux_gpu_name() -> str:
            gpu = _nvidia_gpu_name()
            if gpu:
                return gpu
            try:
                res = subprocess.run(
                    ["lspci"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=3,
                )
                for raw in (res.stdout or "").splitlines():
                    lower = raw.lower()
                    if "vga compatible controller" in lower or "3d controller" in lower or "display controller" in lower:
                        return raw.split(":", 2)[-1].strip()
            except Exception:
                pass
            return ""

        def _linux_device_names() -> tuple[str, str]:
            gpu = _linux_gpu_name() if active_provider in {
                "CUDAExecutionProvider",
                "TensorrtExecutionProvider",
            } else ""
            return gpu, _linux_cpu_name()

        if os.name == "nt":
            gpu_name, cpu_name = _windows_device_names()
        elif sys.platform == "darwin":
            gpu_name, cpu_name = _macos_device_names()
        elif sys.platform.startswith("linux"):
            gpu_name, cpu_name = _linux_device_names()
        else:
            gpu_name, cpu_name = _nvidia_gpu_name(), ""

        self._device_name_cache = {
            "provider": active_provider,
            "gpu": gpu_name,
            "cpu": cpu_name,
            "ts": now,
        }
        return gpu_name, cpu_name

    def _current_mathcraft_pyexe(self) -> str:
        return self._resolve_dynamic_main_pyexe()

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
        else:
            mode_key = self._get_mathcraft_mode_key()
            self.select_model(self._mathcraft_mode_to_model(mode_key))
        self._update_model_desc()
        self._update_mathcraft_visibility()

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
        raw = clean_path_value(raw)
        if not raw:
            return None
        try:
            return normalize_deps_base_dir(Path(raw))
        except Exception:
            return None

    def _resolve_dynamic_main_pyexe(self) -> str:
        env_pyexe = _existing_non_launcher_pyexe_from_env()
        if env_pyexe:
            return env_pyexe

        base_dir = self._current_install_base_dir()
        if base_dir is not None:
            candidate = find_existing_python(base_dir)
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

    def _on_mathcraft_mode_changed(self, index: int):
        if index < 0:
            return
        mode_key = self.mathcraft_mode_combo.itemData(index)
        if self.parent() and hasattr(self.parent(), "cfg"):
            self.parent().cfg.set("mathcraft_mode", mode_key)
        if not self._is_mathcraft_selected():
            return
        self.select_model(self._mathcraft_mode_to_model(mode_key))

    def _update_mathcraft_visibility(self):
        key = None
        idx = self.model_combo.currentIndex()
        if idx >= 0 and idx < len(self._model_options):
            key, _ = self._model_options[idx]
        visible = (key == "mathcraft")
        external_visible = (key == "external_model")
        try:
            self.mathcraft_mode_widget.setVisible(visible)
            self.external_model_widget.setVisible(external_visible)
            self.lbl_compute_mode.setVisible(visible)
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

    def _apply_compute_mode_from_info(self, info: dict, pyexe: str) -> bool:
        if not pyexe or not os.path.exists(pyexe):
            self._set_compute_mode_text("⚪ 计算模式未知", "unknown")
            return True
        if not isinstance(info, dict) or not info:
            return False
        if not info.get("present"):
            self._set_compute_mode_text("⚪ 计算模式未知", "unknown")
            return True
        gpu_active = str(info.get("device") or "").strip().lower() == "gpu"
        gpu_name = str(info.get("gpu_name") or "").strip()
        cpu_name = str(info.get("cpu_name") or "").strip()
        if gpu_active:
            if gpu_name:
                self._set_compute_mode_text(f"🟢 GPU 模式: {gpu_name}", "gpu")
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

        if self._compute_mode_probe_running and not force:
            return

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
