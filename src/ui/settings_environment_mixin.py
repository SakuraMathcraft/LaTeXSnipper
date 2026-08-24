import os
import subprocess
import sys

from qfluentwidgets import MessageBox

from backend.mathcraft.runtime_policy import onnxruntime_cpu_spec, onnxruntime_gpu_policy
from application.restart import build_restart_with_wizard_launch
from runtime.dependency_python import python_env_root
from runtime.environment_terminal import open_main_environment_terminal
from ui.settings_dialog_helpers import (
    _apply_app_window_icon,
    _mathcraft_code_roots,
    _normalize_windows_drive_letter,
)


class SettingsEnvironmentMixin:
    @staticmethod
    def _main_environment_terminal_help(pyexe: str) -> list[str]:
        env_root = python_env_root(pyexe)
        mathcraft_roots = _mathcraft_code_roots()
        doctor_code = (
            "import sys; "
            f"roots={mathcraft_roots!r}; "
            "[sys.path.insert(0, p) for p in reversed(roots) if p not in sys.path]; "
            "from mathcraft_ocr.cli import main; "
            "raise SystemExit(main(['doctor','--provider','cpu']))"
        )
        gpu_command = onnxruntime_gpu_policy(pyexe).pip_command() + " --no-deps"
        cpu_command = f'pip install "{onnxruntime_cpu_spec(pyexe)}"'
        lines = [
            "",
            "================================================================================",
            "                       LaTeXSnipper Terminal - Main Environment",
            "================================================================================",
            "",
            "[*] Env: Main environment (application / MathCraft / core dependencies)",
            f"[*] Python env root: {env_root}",
            "[*] python/pip are bound to this env for this terminal session",
            "",
            "[Model Policy]",
            "  - built-in OCR uses MathCraft model cache",
            "  - external_model uses independently deployed local/online services",
            "  - terminal commands target the current main dependency env",
            "  - MathCraft uses ONNX Runtime providers for the internal OCR path",
            "  - MATHCRAFT_CPU/MATHCRAFT_GPU select CPU/GPU ONNX Runtime backends",
            "",
            "[Version Fix]",
            '  pip install "protobuf>=3.20,<5"',
            "",
            "[ONNX Runtime]",
            f"  {gpu_command}",
            f"  {cpu_command}",
            "",
            "[Model]",
            "  # Step-by-step install (stable order)",
            "  pip install -U pip setuptools wheel --default-timeout 180 --retries 15 --prefer-binary --extra-index-url https://pypi.org/simple",
            '  pip install -U "transformers==4.55.4" "tokenizers==0.21.4" --default-timeout 180 --retries 15 --prefer-binary --extra-index-url https://pypi.org/simple',
            "  # MathCraft is shipped with LaTeXSnipper; the doctor command loads the packaged code roots automatically.",
            '  pip install -U "protobuf>=3.20,<5" "pymupdf~=1.27.2.2" --default-timeout 180 --retries 15 --prefer-binary --extra-index-url https://pypi.org/simple',
            "",
            "[MathCraft CPU/ONNX Check]",
            f'  python -c "{doctor_code}"',
            "",
            "[Diagnostics]",
            "  pip list",
            "  pip check",
            '  python -c "import onnxruntime as ort; print(ort.__version__, ort.get_available_providers())"',
        ]
        if sys.platform != "darwin":
            lines.extend(("  nvidia-smi", "  nvcc --version"))
        lines.extend((
            "",
            "[Cache Clean]",
            "  pip cache purge",
            "",
            "================================================================================",
            "",
        ))
        return lines

    def _open_terminal(self):
        pyexe = self._resolve_dynamic_main_pyexe()
        if not pyexe or not os.path.exists(pyexe):
            self._show_info(
                "环境未就绪",
                "请先在依赖管理向导中初始化依赖环境，再打开主环境终端。",
                "warning",
            )
            return
        if os.name == "nt":
            pyexe = _normalize_windows_drive_letter(pyexe)
        base_dir = self._current_install_base_dir()
        try:
            if open_main_environment_terminal(
                pyexe,
                base_dir or os.path.dirname(pyexe),
                lambda: self._main_environment_terminal_help(pyexe),
            ):
                self._show_info("终端已打开", "已打开主环境终端。", "success")
            else:
                self._show_info("终端已打开", "主环境终端已经在运行。", "info")
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
