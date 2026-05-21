from __future__ import annotations

import json
import os
import subprocess
import threading
from pathlib import Path

from PyQt6.QtGui import QGuiApplication
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from editor.advanced_cas import CasResult
from runtime.dependency_python import resolve_dependency_python


def _hidden_subprocess_kwargs() -> dict:
    if os.name != "nt":
        return {}
    kwargs = {
        "creationflags": int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
    }
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        kwargs["startupinfo"] = startupinfo
    except Exception:
        pass
    return kwargs


class WorkbenchBridge(QObject):
    readyChanged = pyqtSignal(bool)
    latexChanged = pyqtSignal(str)
    mathJsonChanged = pyqtSignal(str)
    resultChanged = pyqtSignal(str)
    statusChanged = pyqtSignal(str)
    insertRequested = pyqtSignal(str)
    typstDisplayReady = pyqtSignal(str)
    conversionWarning = pyqtSignal(str)
    advancedComputeFinished = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ready = False
        self._latex = ""
        self._mathjson = ""
        self._result = ""
        self._advanced_processes: dict[str, subprocess.Popen[str]] = {}

    @property
    def is_ready(self) -> bool:
        return self._ready

    @property
    def latex(self) -> str:
        return self._latex

    @property
    def mathjson(self) -> str:
        return self._mathjson

    @property
    def result(self) -> str:
        return self._result

    @pyqtSlot()
    def onEditorReady(self) -> None:
        self._ready = True
        self.readyChanged.emit(True)
        self.statusChanged.emit("已就绪")

    @pyqtSlot(str)
    def onLatexChanged(self, latex: str) -> None:
        self._latex = latex or ""
        self.latexChanged.emit(self._latex)

    @pyqtSlot(str)
    def onMathJsonChanged(self, payload: str) -> None:
        self._mathjson = payload or ""
        self.mathJsonChanged.emit(self._mathjson)

    @pyqtSlot(str)
    def onEvaluationResult(self, payload: str) -> None:
        self._result = payload or ""
        self.resultChanged.emit(self._result)

    @pyqtSlot(str)
    def onComputeError(self, message: str) -> None:
        self.statusChanged.emit(message or "计算失败")

    @pyqtSlot(str)
    def requestInsertToMain(self, latex: str) -> None:
        text = (latex or "").strip()
        if not text:
            self.statusChanged.emit("提示: 数学工作台为空，没有可写回的内容")
            return
        self.insertRequested.emit(text)

    @staticmethod
    def _format_name() -> str:
        try:
            from backend.latex_renderer import get_document_render_mode
            return "Typst" if get_document_render_mode() == "typst" else "LaTeX"
        except Exception:
            return "LaTeX"

    @pyqtSlot(str)
    def copyLatexToClipboard(self, latex: str) -> None:
        text = latex or ""
        fmt = self._format_name()
        try:
            clipboard = QGuiApplication.clipboard()
            if clipboard is not None:
                clipboard.setText(text)
            self.statusChanged.emit(f"已复制 {fmt}")
        except Exception:
            try:
                import pyperclip

                pyperclip.copy(text)
                self.statusChanged.emit(f"已复制 {fmt}")
            except Exception as e:
                self.statusChanged.emit(f"{fmt} 复制失败：{e}")

    @pyqtSlot(str)
    def copyMathJsonToClipboard(self, payload: str) -> None:
        text = payload or ""
        try:
            clipboard = QGuiApplication.clipboard()
            if clipboard is not None:
                clipboard.setText(text)
            self.statusChanged.emit("已复制 MathJSON")
        except Exception:
            try:
                import pyperclip

                pyperclip.copy(text)
                self.statusChanged.emit("已复制 MathJSON")
            except Exception as e:
                self.statusChanged.emit(f"MathJSON 复制失败：{e}")

    @pyqtSlot(str)
    def convertLatexForDisplay(self, latex: str) -> None:
        text = (latex or "").strip()
        if not text:
            self.typstDisplayReady.emit("")
            return
        try:
            from core.mathcraft_document_engine import convert_latex_to_typst
            typst = convert_latex_to_typst(text)
            self.typstDisplayReady.emit(typst)
            # Verify the conversion didn't lose structural content.
            warning = self._verify_typst_conversion(text, typst)
            if warning:
                self.conversionWarning.emit(warning)
        except Exception:
            self.typstDisplayReady.emit(text)

    @staticmethod
    def _count_latex_structures(latex: str) -> dict:
        """Count key LaTeX structural elements for comparison."""
        import re
        return {
            'frac': len(re.findall(r'\\frac\{', latex)),
            'sqrt': len(re.findall(r'\\sqrt\b', latex)),
            'sum': len(re.findall(r'\\sum\b', latex)),
            'prod': len(re.findall(r'\\prod\b', latex)),
            'int': len(re.findall(r'\\int\b', latex)),
            'lim': len(re.findall(r'\\lim\b', latex)),
            'sin': len(re.findall(r'\\sin\b', latex)),
            'cos': len(re.findall(r'\\cos\b', latex)),
            'tan': len(re.findall(r'\\tan\b', latex)),
            'log': len(re.findall(r'\\log\b', latex)),
            'ln': len(re.findall(r'\\ln\b', latex)),
            'exp': len(re.findall(r'\\exp\b', latex)),
            'matrix': len(re.findall(r'\\begin\{[a-zA-Z]*matrix\}', latex)),
            'cases': len(re.findall(r'\\begin\{cases\}', latex)),
            'binom': len(re.findall(r'\\binom\{', latex)),
            # Count superscripts (^{...} or ^single-char, excluding ^\prime etc)
            'sup': len(re.findall(r'\^(?:\{[^}]*\}|[a-zA-Z0-9])', latex)),
            'sub': len(re.findall(r'_(?:\{[^}]*\}|[a-zA-Z0-9])', latex)),
        }

    @classmethod
    def _verify_typst_conversion(cls, original_latex: str, converted_typst: str) -> str | None:
        """Verify Typst conversion by round-tripping and comparing structure counts.

        Returns a warning message if structural elements were lost, or None
        if the conversion looks good.
        """
        if not original_latex or not converted_typst:
            return None
        try:
            from exporting.formula_converters import convert_typst_to_latex
            back_latex = convert_typst_to_latex(converted_typst)
            if not back_latex or not back_latex.strip():
                return None

            orig_counts = cls._count_latex_structures(original_latex)
            back_counts = cls._count_latex_structures(back_latex)

            # Check for structural losses: any key where orig > back
            lost = []
            for key in orig_counts:
                if orig_counts[key] > back_counts[key]:
                    lost.append((key, orig_counts[key] - back_counts[key]))

            if lost:
                lost_desc = ', '.join(
                    f"{key}(-{diff})" for key, diff in lost
                )
                return f"Typst 转换校验: 以下结构可能丢失 → {lost_desc}"

            return None
        except Exception:
            return None

    @pyqtSlot(result=str)
    def readClipboardText(self) -> str:
        try:
            clipboard = QGuiApplication.clipboard()
            if clipboard is not None:
                return clipboard.text() or ""
        except Exception:
            pass
        try:
            import pyperclip
            return pyperclip.paste() or ""
        except Exception:
            return ""

    @pyqtSlot(str, result=bool)
    def writeClipboardText(self, text: str) -> bool:
        payload = text or ""
        try:
            clipboard = QGuiApplication.clipboard()
            if clipboard is not None:
                clipboard.setText(payload)
                return True
        except Exception:
            pass
        try:
            import pyperclip
            pyperclip.copy(payload)
            return True
        except Exception:
            return False

    @pyqtSlot(str, str, str)
    def requestAdvancedCompute(self, request_id: str, action: str, mathjson_payload: str) -> None:
        rid = (request_id or "").strip()
        act = (action or "").strip()
        payload = mathjson_payload or ""
        if not rid or not act:
            return
        self.statusChanged.emit("正在调用本地高级求解引擎...")
        request_payload = json.dumps(
            {
                "action": act,
                "latex": self._latex,
                "mathjson": payload,
            },
            ensure_ascii=False,
        )

        def wait_worker() -> None:
            process: subprocess.Popen[str] | None = None
            try:
                process = subprocess.Popen(
                    self._advanced_worker_command(),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=str(self._advanced_worker_cwd()),
                    env=self._advanced_worker_env(),
                    **_hidden_subprocess_kwargs(),
                )
                self._advanced_processes[rid] = process
                stdout, stderr = process.communicate(request_payload, timeout=60)
                if process.returncode != 0:
                    detail = (stderr or stdout or "高级引擎子进程异常退出").strip()
                    payload_json = CasResult.from_exception(f"本地高级求解进程失败：{detail}").to_json()
                else:
                    payload_json = (stdout or "").strip()
                    if not payload_json:
                        detail = (stderr or "高级引擎未返回结果").strip()
                        payload_json = CasResult.from_exception(f"本地高级求解进程失败：{detail}").to_json()
            except Exception as e:
                payload_json = CasResult.from_exception(f"本地高级求解进程超时或失败：{e}").to_json()
            finally:
                try:
                    if process is not None and process.poll() is None:
                        process.kill()
                except Exception:
                    pass
                self._advanced_processes.pop(rid, None)
            self.advancedComputeFinished.emit(rid, payload_json)

        threading.Thread(target=wait_worker, daemon=True).start()

    def _advanced_worker_command(self) -> list[str]:
        python_exe = self._resolve_worker_python()
        script_path = Path(__file__).resolve().with_name("advanced_cas.py")
        return [python_exe, str(script_path)]

    def _advanced_worker_cwd(self) -> Path:
        return Path(__file__).resolve().parents[2]

    def _advanced_worker_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["LATEXSNIPPER_ADV_CAS_WORKER"] = "1"
        return env

    def _resolve_worker_python(self) -> str:
        return resolve_dependency_python(fallback_to_current=True)
