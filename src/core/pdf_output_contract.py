# -*- coding: utf-8 -*-
"""Pure PDF output formatting contract for regression testing."""


def wrap_document_output(content: str, fmt_key: str, style_key: str) -> str:
    text = (content or "").strip()
    if not text:
        return ""

    if fmt_key == "markdown":
        if style_key == "paper":
            return "# Title\n\n## Abstract\n\n" + text + "\n\n## References\n"
        return "# Title\n\n" + text

    # LaTeX
    if "\\documentclass" in text and "\\begin{document}" in text:
        return text

    if style_key == "journal":
        docclass = "\\documentclass[journal]{IEEEtran}"
    else:
        docclass = "\\documentclass[11pt]{article}"

    preamble = (
        f"{docclass}\n"
        "\\usepackage{amsmath,amssymb}\n"
        "\\usepackage{geometry}\n"
        "\\geometry{a4paper, margin=1in}\n"
        "\\begin{document}\n"
    )
    return preamble + text + "\n\\end{document}\n"

