"""Exercise frozen PDF, XML and bundled MathJax resources before publication."""

import json
from pathlib import Path


def validate_application(output: Path) -> None:
    from runtime.main_preflight import pre_bootstrap_runtime

    pre_bootstrap_runtime()
    import fitz
    import lxml.etree as etree
    import psutil
    from PyQt6.QtCore import QCoreApplication, QEvent
    from PyQt6.QtWidgets import QApplication

    from runtime.webengine_runtime import ensure_webengine_loaded

    if not ensure_webengine_loaded():
        raise RuntimeError("Packaged Qt WebEngine runtime failed validation")

    from exporting import mathjax_converter

    application = QApplication.instance() or QApplication(
        ["LaTeXSnipper-resource-validation"]
    )
    traffic = psutil.net_io_counters()
    if traffic is None or traffic.bytes_recv < 0 or traffic.bytes_sent < 0:
        raise RuntimeError("Packaged network speed monitor failed validation")
    document = fitz.open()
    document.new_page().insert_text((30, 30), "LaTeXSnipper PDF OCR")
    encoded = document.tobytes()
    document.close()
    with fitz.open(stream=encoded, filetype="pdf") as decoded:
        if "PDF OCR" not in decoded[0].get_text():
            raise RuntimeError("Packaged PDF runtime failed validation")
    result = mathjax_converter.convert_latex_with_mathjax(r"\int_0^1 x^2\,dx")
    for name in ("svg", "mathml"):
        etree.fromstring(result[name].encode("utf-8"))
    output.write_text(
        json.dumps(
            {
                "pdf": True,
                "xml": True,
                "mathjax_svg": True,
                "mathjax_mathml": True,
                "network_speed": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    if mathjax_converter._converter is not None:
        mathjax_converter._converter._page.deleteLater()
        mathjax_converter._converter = None
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    application.processEvents()
