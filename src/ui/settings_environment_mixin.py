import os
import subprocess
import sys

from qfluentwidgets import MessageBox

from backend.cuda_runtime_policy import onnxruntime_cpu_spec, onnxruntime_gpu_policy
from core.restart_contract import build_restart_with_wizard_launch
from ui.settings_dialog_helpers import (
    _apply_app_window_icon,
    _hidden_subprocess_kwargs,
    _subprocess_creationflags,
)


class SettingsEnvironmentMixin:

    def _get_terminal_env_key(self) -> str:
        return "main"

    def _onnxruntime_cpu_spec(self) -> str:
        return onnxruntime_cpu_spec(self._current_mathcraft_pyexe())

    def _onnxruntime_gpu_command(self) -> str:
        return onnxruntime_gpu_policy(self._current_mathcraft_pyexe()).pip_command() + " --no-deps"

    def _open_terminal(self, env_key: str | None = None):
        if isinstance(env_key, bool):
            env_key = None
        import subprocess
        import os
        if env_key is None:
            env_key = self._get_terminal_env_key()
        # Always open only the main environment terminal.
        env_key = "main"
        _dbg_text = "主环境"
        _dbg_idx = 0
        print(f"[DEBUG] Terminal select: text={_dbg_text!r} idx={_dbg_idx} env_key={env_key}")
        
        pyexe = self._resolve_dynamic_main_pyexe()
        print(f"[DEBUG] Terminal pyexe initial: {pyexe}")
        if not pyexe or not os.path.exists(pyexe):
            msg = MessageBox(
                "环境未就绪",
                "当前依赖目录尚未初始化 Python 环境。\n\n请先在【依赖管理向导】中初始化依赖环境，再打开环境终端。",
                self,
            )
            _apply_app_window_icon(msg)
            msg.yesButton.setText("OK")
            msg.cancelButton.hide()
            msg.exec()
            return
        env_root = self._python_env_root(pyexe)
        pyexe_dir = str(env_root)
        scripts_dir = os.path.join(pyexe_dir, "Scripts")
        base_dir = self._current_install_base_dir()
        venv_dir = str(base_dir or env_root)
        env_name = {
            "main": "主环境",
        }.get(env_key, "主环境")
        msg = MessageBox(
            "打开环境终端",
            "是否以管理员模式打开终端？\n\n"
            "- 管理员：推荐用于修复权限问题\n"
            "- 普通：快速打开，可能遇到权限错误\n"
            "- ESC：取消",
            self
        )
        _apply_app_window_icon(msg)
        msg.yesButton.setText("管理员")
        msg.cancelButton.setText("普通")
        esc_pressed = [False]
        from PyQt6.QtCore import Qt as QtCore_Qt
        from PyQt6.QtGui import QKeyEvent
        original_keyPressEvent = msg.keyPressEvent
        def custom_keyPressEvent(event: QKeyEvent):
            if event.key() == QtCore_Qt.Key.Key_Escape:
                esc_pressed[0] = True
                msg.close()
            else:
                original_keyPressEvent(event)
        msg.keyPressEvent = custom_keyPressEvent
        result = msg.exec()
        if esc_pressed[0]:
            return
        as_admin = result
        env_desc = "主环境（程序 / MathCraft / 核心依赖）"
        gpu_onnx_cmd = self._onnxruntime_gpu_command()
        cpu_onnx_cmd = f'pip install "{self._onnxruntime_cpu_spec()}"'
        help_lines = [
            "echo.",
            "echo ================================================================================",
            f"echo                        LaTeXSnipper Terminal - {env_name}",
            "echo ================================================================================",
            "echo.",
            f"echo [*] Env: {env_desc}",
            f"echo [*] Python env root: {pyexe_dir}",
            "echo [*] python/pip are bound to this env for this terminal session",
            "echo.",
            "echo [Model Policy]",
            "echo   - built-in OCR uses MathCraft model cache",
            "echo   - external_model uses independently deployed local/online services",
            "echo   - terminal commands target the current main dependency env",
            "echo   - MathCraft uses ONNX Runtime providers for the internal OCR path",
            "echo   - MATHCRAFT_CPU/MATHCRAFT_GPU select CPU/GPU ONNX Runtime backends",
            "echo.",
            "echo [Version Fix]",
            "echo   pip install \"protobuf>=3.20,<5\"",
            "echo.",
            "echo [ONNX Runtime]",
            f"echo   {gpu_onnx_cmd}",
            f"echo   {cpu_onnx_cmd}",
            "echo.",
            "echo [Model]",
            "echo   # Step-by-step install (stable order)",
            "echo   pip install -U pip setuptools wheel --default-timeout 180 --retries 15 --prefer-binary --extra-index-url https://pypi.org/simple",
            "echo   pip install -U \"transformers==4.55.4\" \"tokenizers==0.21.4\" --default-timeout 180 --retries 15 --prefer-binary --extra-index-url https://pypi.org/simple",
            "echo   # MathCraft is shipped with LaTeXSnipper source/package; verify it from the project root.",
            "echo   pip install -U \"protobuf>=3.20,<5\" \"pymupdf~=1.27.2.2\" --default-timeout 180 --retries 15 --prefer-binary --extra-index-url https://pypi.org/simple",
            "echo.",
            "echo [MathCraft CPU/ONNX Check]",
            "echo   python -c \"import sys; sys.path.insert(0, r'%CD%'); from mathcraft_ocr.cli import main; raise SystemExit(main(['doctor','--provider','cpu']))\"",
            "echo.",
        ]
        help_lines += [
            "echo [Diagnostics]",
            "echo   pip list",
            "echo   pip check",
            "echo   python -c \"import onnxruntime as ort; print(ort.__version__, ort.get_available_providers())\"",
            "echo   nvidia-smi",
            "echo   nvcc --version",
            "echo.",
            "echo [Cache Clean]",
            "echo   pip cache purge",
            "echo.",
            "echo ================================================================================",
            "echo.",
        ]
        help_text = "\n".join(help_lines) + "\n"
        python_bind_lines = (
            f'set "LATEXSNIPPER_PYEXE={pyexe}"\n'
            f'doskey python="{pyexe}" $*\n'
            f'doskey py="{pyexe}" $*\n'
            f'doskey pip="{pyexe}" -m pip $*\n'
            "echo [*] python macro : %LATEXSNIPPER_PYEXE%\n"
            "echo [*] pip macro    : %LATEXSNIPPER_PYEXE% -m pip\n"
            "echo.\n"
        )
        try:
            if as_admin:
                import tempfile
                batch_content = ("@echo off\n"
                    + f'cd /d "{venv_dir}"\n'
                    + f'set "PATH={pyexe_dir};{scripts_dir};%PATH%"\n'
                    + python_bind_lines
                    + help_text
                )
                with tempfile.NamedTemporaryFile(mode="w", suffix=".bat", delete=False, encoding="mbcs", newline="\r\n") as f:
                    f.write(batch_content)
                    batch_path = f.name
                import ctypes
                ctypes.windll.shell32.ShellExecuteW(
                    None, "runas", "cmd.exe", f"/k \"{batch_path}\"", None, 1
                )
                self._show_info("终端已打开", "已弹出 UAC 授权提示。", "success")
            else:
                import tempfile
                batch_content_normal = ("@echo off\n"
                    + f'cd /d "{venv_dir}"\n'
                    + f'set "PATH={pyexe_dir};{scripts_dir};%PATH%"\n'
                    + python_bind_lines
                    + help_text
                )
                with tempfile.NamedTemporaryFile(mode="w", suffix=".bat", delete=False, encoding="mbcs", newline="\r\n") as f:
                    f.write(batch_content_normal)
                    batch_path = f.name
                subprocess.Popen(
                    ["cmd.exe", "/k", batch_path],
                    cwd=venv_dir,
                    creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
                )
                self._show_info("终端已打开", "已以普通模式打开。", "success")
        except Exception as e:
            self._show_info("终端打开失败", str(e), "error")

    def _resolve_mathcraft_cache_dir(self) -> str:
        appdata = (os.environ.get("APPDATA", "") or "").strip()
        if appdata:
            return os.path.normpath(os.path.join(appdata, "MathCraft", "models"))
        return os.path.normpath(os.path.expanduser("~/.MathCraft/models"))

    def _open_mathcraft_cache_dir(self):
        path = self._resolve_mathcraft_cache_dir()
        try:
            os.makedirs(path, exist_ok=True)
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
            self._show_info("已打开", f"MathCraft 缓存目录: {path}", "success")
        except Exception as e:
            self._show_info("打开失败", f"无法打开缓存目录: {e}", "error")

    def _open_deps_wizard(self):
        """Open the dependency management wizard."""
        msg = MessageBox(
            "打开依赖向导",
            "依赖管理向导将以重启后的干净进程打开。\n\n是否立即重启并打开依赖向导？\n• ESC取消操作",
            self
        )
        _apply_app_window_icon(msg)
        msg.yesButton.setText("重启并打开")
        msg.cancelButton.setText("取消")

        esc_pressed = [False]
        from PyQt6.QtCore import Qt as QtCore_Qt
        from PyQt6.QtGui import QKeyEvent
        original_keyPressEvent = msg.keyPressEvent

        def custom_keyPressEvent(event: QKeyEvent):
            if event.key() == QtCore_Qt.Key.Key_Escape:
                esc_pressed[0] = True
                msg.close()
            else:
                original_keyPressEvent(event)

        msg.keyPressEvent = custom_keyPressEvent
        result = msg.exec()
        if esc_pressed[0] or not result:
            return
        self._restart_with_wizard()

    def _restart_with_wizard(self):
        """Restart the app and open the dependency wizard."""
        import sys
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QCoreApplication
        import os

        argv0 = ""
        try:
            argv0 = QCoreApplication.applicationFilePath() or ""
        except Exception:
            argv0 = ""
        exe_name = os.path.basename(argv0).lower() if argv0 else ""
        if (not argv0) or exe_name in ("python.exe", "pythonw.exe", "python", "pythonw"):
            argv0 = os.path.abspath(sys.argv[0]) if sys.argv else ""
        spawn_argv, env = build_restart_with_wizard_launch(
            python_exe=sys.executable,
            argv0=argv0,
            base_env=os.environ.copy(),
        )
        try:
            # Release heavy resources and the instance lock first to reduce the chance that the new process cannot acquire the lock.
            parent = self.parent()
            if parent and hasattr(parent, "prepare_restart"):
                try:
                    parent.prepare_restart()
                except Exception:
                    pass
            try:
                app = QApplication.instance()
                if app:
                    app.processEvents()
            except Exception:
                pass
            spawn_flags = int(_subprocess_creationflags()) if getattr(sys, "frozen", False) else 0
            popen_kwargs = _hidden_subprocess_kwargs() if spawn_flags else {}
            subprocess.Popen([str(x) for x in spawn_argv], env=env, **popen_kwargs)
            # Close the current program.
            QApplication.instance().quit()
        except Exception as e:
            from qfluentwidgets import InfoBar, InfoBarPosition
            InfoBar.error(
                title="重启失败",
                content=f"无法重启程序: {e}",
                parent=self,
                duration=5000,
                position=InfoBarPosition.TOP
            )

    def _show_info(self, title: str, content: str, level: str = "info"):
        """Show a Fluent floating notification."""
        from qfluentwidgets import InfoBar, InfoBarPosition
        # Anchor to the settings window to avoid covering the main window.
        parent = self
        func = getattr(InfoBar, level, InfoBar.info)
        func(
            title=title,
            content=content,
            parent=parent,
            duration=4000,
            position=InfoBarPosition.TOP
        )
