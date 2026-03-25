from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

from PyQt6.QtGui import QGuiApplication
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from editor.advanced_cas import CasResult


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
        if text:
            self.insertRequested.emit(text)

    @pyqtSlot(str)
    def copyLatexToClipboard(self, latex: str) -> None:
        text = latex or ""
        try:
            clipboard = QGuiApplication.clipboard()
            if clipboard is not None:
                clipboard.setText(text)
            self.statusChanged.emit("已复制 LaTeX")
        except Exception:
            try:
                import pyperclip

                pyperclip.copy(text)
                self.statusChanged.emit("已复制 LaTeX")
            except Exception as e:
                self.statusChanged.emit(f"LaTeX 复制失败：{e}")

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
        pyexe = (os.environ.get("LATEXSNIPPER_PYEXE", "") or "").strip()
        if pyexe and os.path.exists(pyexe):
            return pyexe
        return sys.executable
