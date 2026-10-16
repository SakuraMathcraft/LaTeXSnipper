"""Exercise frozen PDF, XML and bundled MathJax resources before publication."""

import json
from pathlib import Path


def validate_application(output: Path) -> None:
    from runtime.main_preflight import pre_bootstrap_runtime

    pre_bootstrap_runtime()
    import fitz
    from lxml import etree
    from PyQt6.QtCore import QCoreApplication, QEvent
    from PyQt6.QtWidgets import QApplication
    from exporting import mathjax_converter
    application = QApplication.instance() or QApplication(['LaTeXSnipper-resource-validation'])
    document = fitz.open()
    document.new_page().insert_text((30, 30), 'LaTeXSnipper PDF OCR')
    encoded = document.tobytes()
    document.close()
    with fitz.open(stream=encoded, filetype='pdf') as decoded:
        if 'PDF OCR' not in decoded[0].get_text():
            raise RuntimeError('Packaged PDF runtime failed validation')
    result = mathjax_converter.convert_latex_with_mathjax(r'\int_0^1 x^2\,dx')
    for name in ('svg', 'mathml'):
        etree.fromstring(result[name].encode('utf-8'))
    output.write_text(json.dumps({'pdf': True, 'xml': True, 'mathjax_svg': True, 'mathjax_mathml': True}) + '\n', encoding='utf-8')
    if mathjax_converter._converter is not None:
        mathjax_converter._converter._page.deleteLater()
        mathjax_converter._converter = None
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    application.processEvents()
