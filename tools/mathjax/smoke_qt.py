"""Exercise the production Qt conversion bridge and CHTML pages (no visible UI)."""

from pathlib import Path
import json
import os
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")

from PyQt6.QtWebEngineCore import QWebEngineSettings  # noqa: E402
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: E402,F401
from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtCore import QCoreApplication, QEvent, QUrl  # noqa: E402
from exporting.mathjax_converter import _MathJaxConverter  # noqa: E402
from exporting.pandoc_exporter import convert_latex_to  # noqa: E402
from preview.math_preview import build_math_html  # noqa: E402
from preview.content_preview import build_mixed_content_html  # noqa: E402
from preview.smart_preview import build_smart_preview_html  # noqa: E402
from handwriting.latex_preview import build_handwriting_preview_html  # noqa: E402
from rendering.mathjax_runtime import ASSET_ROOT, loader_script, cdn_root  # noqa: E402


def main() -> None:
    app = QApplication(['mathjax-smoke'])
    converter = _MathJaxConverter()
    samples = [r'\ce{CO2 + C -> 2 CO}', r'\mathrm{\delta}',
               r'\begin{align}&\text{设 }A,B\text{ 为事件}\\&P(A\mid B)=\frac{P(A\cap B)}{P(B)}\end{align}']
    for source in samples:
        result = converter.convert(source, ('mathml', 'svg'))
        assert 'data-mjx-error' not in result['svg'] and '<merror' not in result['mathml']
    base = QUrl.fromLocalFile(str(ASSET_ROOT) + '/')
    exported = convert_latex_to('pandoc_html_standalone', r'\[\ce{CO2 + C -> 2 CO}\]')
    assert cdn_root() in exported and '\\ce{CO2 + C' in exported
    pages = [build_math_html(samples[-1]), build_mixed_content_html('混排 $x^2$'),
             build_smart_preview_html([('x', 'Formula', 'mathcraft')]),
             build_handwriting_preview_html('手写结果 $x^2$', 'markdown'),
             exported,
             '<html><head>' + loader_script(font='mathjax-stix2')
             + '</head><body>$\\mathbb{ABC}$</body></html>']
    for html in pages:
        converter._page.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, html == exported)
        assert converter._wait_for_signal(converter._page.loadFinished,
                                         lambda: converter._page.setHtml(html, base), timeout_ms=15000)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            state = converter._run_javascript(
                "JSON.stringify({error:window.LaTeXSnipperMathJax?.error,"
                "ready:window.LaTeXSnipperMathJax?.ready,"
                "count:document.querySelectorAll('mjx-container[jax=CHTML]').length,"
                "errors:document.querySelectorAll('mjx-merror').length})")
            data = json.loads(state)
            assert not data.get('error'), data
            if data.get('ready') and data['count']:
                assert not data['errors'], data
                # Exercise actual font loading, not just creation of CHTML nodes.
                converter._run_javascript("document.fonts.ready.then(() => window.fontsReady = true)")
                while time.monotonic() < deadline:
                    if converter._run_javascript("window.fontsReady === true"):
                        break
                    converter._pause()
                else:
                    raise AssertionError('CHTML font loading timed out')
                break
            converter._pause()
        else:
            raise AssertionError(f'CHTML page failed to typeset: {state}')
    converter._view.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    print(f'Qt smoke passed: {len(samples)} SVG/MathML conversions, {len(pages)} CHTML pages.')


if __name__ == '__main__':
    main()
