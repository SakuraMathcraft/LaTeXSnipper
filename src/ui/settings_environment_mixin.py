import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from qfluentwidgets import MessageBox

from backend.cuda_runtime_policy import onnxruntime_cpu_spec, onnxruntime_gpu_policy
from core.restart_contract import build_restart_with_wizard_launch
from runtime.app_paths import app_temp_dir
from ui.settings_dialog_helpers import (
    _apply_app_window_icon,
    _normalize_windows_drive_letter,
)


class SettingsEnvironmentMixin:

    def _terminal_launcher_dir(self) -> Path:
        path = app_temp_dir() / "terminal-launchers"
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _get_terminal_env_key(self) -> str:
        return "main"

    def _onnxruntime_cpu_spec(self) -> str:
        return onnxruntime_cpu_spec(self._current_mathcraft_pyexe())

    def _onnxruntime_gpu_command(self) -> str:
        return onnxruntime_gpu_policy(self._current_mathcraft_pyexe()).pip_command() + " --no-deps"

    def _open_terminal(self, env_key: str | None = None):
        if isinstance(env_key, bool):
            env_key = None
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
        if os.name == "nt":
            pyexe = _normalize_windows_drive_letter(pyexe)
        env_root = self._python_env_root(pyexe)
        pyexe_dir = str(env_root)
        scripts_dir = os.path.join(pyexe_dir, "Scripts")
        base_dir = self._current_install_base_dir()
        venv_dir = str(base_dir or env_root)
        project_root = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".."))
        env_name = {
            "main": "主环境",
        }.get(env_key, "主环境")
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
            f"echo   # MathCraft is shipped with LaTeXSnipper source/package; project root: {project_root}",
            "echo   pip install -U \"protobuf>=3.20,<5\" \"pymupdf~=1.27.2.2\" --default-timeout 180 --retries 15 --prefer-binary --extra-index-url https://pypi.org/simple",
            "echo.",
            "echo [MathCraft CPU/ONNX Check]",
            f"echo   python -c \"import sys; sys.path.insert(0, r'{project_root}'); from mathcraft_ocr.cli import main; raise SystemExit(main(['doctor','--provider','cpu']))\"",
            "echo.",
        ]
        diagnostics_lines = [
            "echo [Diagnostics]",
            "echo   pip list",
            "echo   pip check",
            "echo   python -c \"import onnxruntime as ort; print(ort.__version__, ort.get_available_providers())\"",
        ]
        if sys.platform != "darwin":
            diagnostics_lines += [
                "echo   nvidia-smi",
                "echo   nvcc --version",
            ]
        diagnostics_lines += [
            "echo.",
            "echo [Cache Clean]",
            "echo   pip cache purge",
            "echo.",
            "echo ================================================================================",
            "echo.",
        ]
        help_lines += diagnostics_lines
        try:
            launcher_dir = self._terminal_launcher_dir()

            if os.name == "nt":
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
                batch_content = (
                    "@echo off\n"
                    + f'cd /d "{venv_dir}"\n'
                    + f'set "PATH={pyexe_dir};{scripts_dir};%PATH%"\n'
                    + python_bind_lines
                    + help_text
                )
                batch_path = launcher_dir / "latexsnipper-terminal.bat"
                with open(batch_path, "w", encoding="mbcs", newline="\r\n") as f:
                    f.write(batch_content)
                subprocess.Popen(
                    ["cmd.exe", "/k", str(batch_path)],
                    cwd=venv_dir,
                    creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
                )
            else:
                wrapper_dir_path = launcher_dir / "bin"
                wrapper_dir_path.mkdir(parents=True, exist_ok=True)
                wrapper_dir = str(wrapper_dir_path)
                for name, command in {
                    "python": f'exec {shlex.quote(pyexe)} "$@"\n',
                    "py": f'exec {shlex.quote(pyexe)} "$@"\n',
                    "pip": f'exec {shlex.quote(pyexe)} -m pip "$@"\n',
                }.items():
                    wrapper_path = os.path.join(wrapper_dir, name)
                    with open(wrapper_path, "w", encoding="utf-8", newline="\n") as f:
                        f.write("#!/bin/sh\n" + command)
                    os.chmod(wrapper_path, 0o755)

                shell_help_lines = []
                for line in help_lines:
                    if line == "echo.":
                        shell_help_lines.append("")
                    elif line.startswith("echo "):
                        shell_help_lines.append(line[5:])
                    else:
                        shell_help_lines.append(line)
                shell_help = "\n".join(shell_help_lines)
                pyexe_bin = os.path.dirname(pyexe)
                path_prefix = os.pathsep.join(
                    item for item in (wrapper_dir, pyexe_bin, os.environ.get("PATH", "")) if item
                )
                script_suffix = ".command" if sys.platform == "darwin" else ".sh"
                script_path = launcher_dir / f"latexsnipper-terminal{script_suffix}"
                with open(script_path, "w", encoding="utf-8", newline="\n") as f:
                    f.write(
                        "#!/bin/sh\n"
                        f"cd {shlex.quote(venv_dir)} || exit 1\n"
                        f"export LATEXSNIPPER_PYEXE={shlex.quote(pyexe)}\n"
                        f"export PATH={shlex.quote(path_prefix)}\n"
                        "cat <<'LATEXSNIPPER_HELP'\n"
                        f"{shell_help}\n"
                        "LATEXSNIPPER_HELP\n"
                        "echo \"[*] python command: $(command -v python)\"\n"
                        "echo \"[*] pip command   : $(command -v pip)\"\n"
                        "echo\n"
                        "exec \"${SHELL:-/bin/sh}\" -i\n"
                    )
                os.chmod(script_path, 0o755)

                if sys.platform == "darwin":
                    subprocess.Popen(["open", str(script_path)], cwd=venv_dir)
                else:
                    launchers = []
                    env_terminal = os.environ.get("TERMINAL", "").strip()
                    if env_terminal:
                        launchers.append([env_terminal, "-e", script_path])
                    launchers.extend([
                        ["x-terminal-emulator", "-e", script_path],
                        ["gnome-terminal", "--", script_path],
                        ["konsole", "-e", script_path],
                        ["xfce4-terminal", "-e", script_path],
                        ["xterm", "-e", script_path],
                    ])
                    for launcher in launchers:
                        if shutil.which(launcher[0]):
                            subprocess.Popen(launcher, cwd=venv_dir)
                            break
                    else:
                        raise RuntimeError("No supported terminal emulator was found.")
            self._show_info("终端已打开", "已打开当前依赖环境终端。", "success")
        except Exception as e:
            self._show_info("终端打开失败", str(e), "error")

    def _resolve_mathcraft_cache_dir(self) -> str:
        from mathcraft_ocr.cache import resolve_user_models_dir

        return os.path.normpath(str(resolve_user_models_dir()))

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
            "依赖管理向导将以重启后的干净进程打开。\n\n是否立即重启并打开依赖向导？\n• ESC：取消操作",
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
            # This launches the GUI app itself.  Passing SW_HIDE here can hide the
            # child process' first Qt window, which is the dependency wizard.
            subprocess.Popen([str(x) for x in spawn_argv], env=env)
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

    def _cleanup_macos_local_data(self):
        """Remove macOS user-scoped dependency data without touching app settings."""
        if sys.platform != "darwin":
            self._show_info("清理不可用", "本清理入口仅适用于 macOS。", "info")
            return

        from runtime.macos_local_data_cleanup import cleanup_macos_local_data, macos_cleanup_targets

        target_lines = "\n".join(f"• {path}" for path in macos_cleanup_targets())
        msg = MessageBox(
            "清理本机依赖与缓存",
            "这会移除 LaTeXSnipper 在本机下载的依赖、缓存和日志。\n"
            "应用本身和设置会保留；下次使用内置识别时可能需要重新下载依赖。\n\n"
            f"将清理：\n{target_lines}\n\n是否继续？",
            self,
        )
        _apply_app_window_icon(msg)
        msg.yesButton.setText("清理")
        msg.cancelButton.setText("取消")

        if not msg.exec():
            return

        result = cleanup_macos_local_data()
        if result.failed:
            first_path, first_error = result.failed[0]
            self._show_info(
                "清理未完成",
                f"{len(result.failed)} 个项目清理失败。示例：{first_path}: {first_error}",
                "error",
            )
            return
        if result.removed:
            self._show_info(
                "清理完成",
                f"已清理 {len(result.removed)} 个项目；应用设置已保留，请重启后按需重新下载依赖。",
                "success",
            )
            return
        self._show_info("无需清理", "没有发现已下载的本机依赖、缓存或日志。", "info")

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
