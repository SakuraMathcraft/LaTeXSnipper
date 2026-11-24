"""Exercise frozen PDF, XML and bundled MathJax resources before publication."""

import json
import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from runtime.distribution_manifest import ManifestError, read_json
from runtime.processes import hidden_subprocess_kwargs

if TYPE_CHECKING:
    from runtime.installed_resources import InstalledResources


def run_frozen_application_validation(
    resources: "InstalledResources", output: Path
) -> dict:
    """Check the frozen GUI against the staged application and worker payload."""
    system = resources.manifest.platform
    executable = "LaTeXSnipper.exe" if system == "windows" else "LaTeXSnipper"
    environment = {
        **os.environ,
        "QTWEBENGINE_CHROMIUM_FLAGS": "--disable-gpu --no-sandbox",
    }
    if system == "linux":
        environment["QT_QPA_PLATFORM"] = "offscreen"
    output.unlink(missing_ok=True)
    completed = subprocess.run(
        [
            str(resources.directory("runtime") / executable),
            "--validate-application",
            str(output),
        ],
        check=False,
        env=environment,
        timeout=180,
        **hidden_subprocess_kwargs(),
    )
    report = read_json(output) if output.is_file() else {}
    if completed.returncode or not report:
        detail = report.get("error") or f"exit code {completed.returncode}"
        raise ManifestError(f"Frozen application validation failed: {detail}")
    return report


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
    from recognition.pdf_text import visible_pdf_text

    application = QApplication.instance() or QApplication(
        ["LaTeXSnipper-resource-validation"]
    )
    traffic = psutil.net_io_counters()
    if traffic is None or traffic.bytes_recv < 0 or traffic.bytes_sent < 0:
        raise RuntimeError("Packaged network speed monitor failed validation")
    document = fitz.open()
    page = document.new_page()
    for line in range(4):
        page.insert_text((30, 30 + 20 * line), "LaTeXSnipper PDF OCR")
    encoded = document.tobytes()
    document.close()
    with fitz.open(stream=encoded, filetype="pdf") as decoded:
        lines = visible_pdf_text(
            decoded[0], text_flags=fitz.TEXTFLAGS_RAWDICT, outline=[]
        )
        if (
            not lines
            or "".join(glyph[0] for glyph in lines[0]["glyphs"])
            != "LaTeXSnipper PDF OCR"
        ):
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
