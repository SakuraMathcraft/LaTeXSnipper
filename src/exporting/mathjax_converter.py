"""Local MathJax conversion shared by desktop exports and Office Bridge."""

from __future__ import annotations

import json
from typing import Any

from PyQt6.QtCore import QEventLoop, QThread, QTimer
from PyQt6.QtWidgets import QApplication

from preview.math_preview import get_mathjax_base_url


_CONVERTER_HTML = r"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<script>
window.MathJax = {
  loader: {
    load: ['[tex]/bbox', '[tex]/boldsymbol', '[tex]/color', '[tex]/enclose', '[tex]/mhchem']
  },
  tex: {
    packages: {
      '[+]': ['bbox', 'boldsymbol', 'color', 'enclose', 'mhchem']
    }
  },
  svg: {
    fontCache: 'none'
  },
  startup: {
    typeset: false
  }
};
</script>
<script src="tex-mml-svg.js"></script>
</head>
<body></body>
</html>
"""


class MathJaxConversionError(RuntimeError):
    """Raised when the embedded MathJax conversion runtime fails."""


class _MathJaxConverter:
    def __init__(self) -> None:
        app = QApplication.instance()
        if app is None:
            raise MathJaxConversionError("MathJax export requires a running QApplication")
        if QThread.currentThread() is not app.thread():
            raise MathJaxConversionError("MathJax export must run on the UI thread")

        from PyQt6.QtWebEngineWidgets import QWebEngineView

        self._view = QWebEngineView()
        self._page = self._view.page()
        self._ready = False

    def convert(self, latex: str) -> dict[str, str]:
        self._ensure_ready()
        source = json.dumps(str(latex or ""))
        script = f"""
(() => {{
  try {{
    const source = {source};
    const options = {{ display: true, end: 20 }};
    const mathml = MathJax.tex2mml(source, options);
    const adaptor = MathJax.startup.adaptor;
    const container = MathJax.tex2svg(source, {{ display: true }});
    const svg = adaptor.outerHTML(adaptor.firstChild(container));
    return JSON.stringify({{ mathml, svg }});
  }} catch (error) {{
    return JSON.stringify({{ error: String(error && (error.stack || error.message) || error) }});
  }}
}})()
"""
        raw = self._run_javascript(script)
        if not isinstance(raw, str) or not raw:
            raise MathJaxConversionError("MathJax returned an empty conversion result")
        result = json.loads(raw)
        error = str(result.get("error") or "").strip()
        if error:
            raise MathJaxConversionError(error)
        mathml = str(result.get("mathml") or "").strip()
        svg = str(result.get("svg") or "").strip()
        if not mathml.startswith("<math") or not svg.startswith("<svg"):
            raise MathJaxConversionError("MathJax returned an invalid conversion result")
        return {"mathml": mathml, "svg": svg}

    def _ensure_ready(self) -> None:
        if self._ready:
            return
        loaded = self._wait_for_signal(
            lambda done: self._page.loadFinished.connect(done),
            lambda: self._page.setHtml(_CONVERTER_HTML, get_mathjax_base_url()),
            timeout_ms=15_000,
        )
        if not loaded:
            raise MathJaxConversionError("Failed to load the local MathJax export runtime")

        for _ in range(150):
            ready = self._run_javascript(
                "Boolean(window.MathJax && MathJax.startup && "
                "MathJax.startup.document && MathJax.tex2mml && MathJax.tex2svg)"
            )
            if ready is True:
                self._ready = True
                return
            loop = QEventLoop()
            QTimer.singleShot(50, loop.quit)
            loop.exec()
        raise MathJaxConversionError("Local MathJax export runtime timed out")

    def _run_javascript(self, script: str) -> Any:
        result: list[Any] = []
        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)

        def completed(value: Any) -> None:
            result.append(value)
            loop.quit()

        self._page.runJavaScript(script, completed)
        timer.start(15_000)
        loop.exec()
        if timer.isActive():
            timer.stop()
        if not result:
            raise MathJaxConversionError("MathJax JavaScript execution timed out")
        return result[0]

    @staticmethod
    def _wait_for_signal(connect, start, *, timeout_ms: int) -> bool:
        result: list[bool] = []
        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)

        def completed(ok: bool) -> None:
            result.append(bool(ok))
            loop.quit()

        connect(completed)
        start()
        timer.start(timeout_ms)
        loop.exec()
        if timer.isActive():
            timer.stop()
        return bool(result and result[0])


_converter: _MathJaxConverter | None = None
_last_latex = ""
_last_result: dict[str, str] | None = None


def convert_latex_with_mathjax(latex: str) -> dict[str, str]:
    """Return MathML and standalone SVG generated by the bundled MathJax."""
    global _converter, _last_latex, _last_result
    source = str(latex or "")
    if source == _last_latex and _last_result is not None:
        return dict(_last_result)
    if _converter is None:
        _converter = _MathJaxConverter()
    result = _converter.convert(source)
    _last_latex = source
    _last_result = dict(result)
    return result
