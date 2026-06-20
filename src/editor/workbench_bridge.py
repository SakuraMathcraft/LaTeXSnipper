from __future__ import annotations

from PyQt6.QtGui import QGuiApplication
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot


class WorkbenchBridge(QObject):
    readyChanged = pyqtSignal(bool)
    latexChanged = pyqtSignal(str)
    mathJsonChanged = pyqtSignal(str)
    resultChanged = pyqtSignal(str)
    statusChanged = pyqtSignal(str)
    insertRequested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ready = False
        self._latex = ""
        self._mathjson = ""
        self._result = ""

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
