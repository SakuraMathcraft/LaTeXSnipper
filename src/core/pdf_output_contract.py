# -*- coding: utf-8 -*-
"""Pure PDF output formatting contract for regression testing."""

import re


def wrap_document_output(content: str, fmt_key: str, style_key: str) -> str:
    text = (content or "").strip()
    if not text:
        return ""

    if fmt_key == "markdown":
        return _wrap_markdown_document(text)

    # LaTeX
    if "\\documentclass" in text and "\\begin{document}" in text:
        return text

    return _wrap_latex_document(text)


def _wrap_markdown_document(text: str) -> str:
    normalized = _normalize_markdown_image_placeholders(text.replace("\r\n", "\n").strip())
    header = [
        "<!-- LaTeXSnipper PDF OCR Export -->",
        "<!-- 保留原始标题层级、图片占位、表格与公式结构 -->",
        "<!-- 图片占位统一标记: [IMAGE_PLACEHOLDER: 描述] -->",
        "",
    ]
    return "\n".join(header) + normalized + "\n"


def _normalize_markdown_image_placeholders(text: str) -> str:
    if not text:
        return ""

    pattern = re.compile(r"^\[(图片|插图|示意图|流程图)\]\s*(.*)$")
    normalized_lines: list[str] = []
    for raw_line in text.split("\n"):
        line = raw_line.rstrip()
        match = pattern.match(line.strip())
        if not match:
            normalized_lines.append(raw_line)
            continue
        kind = match.group(1)
        desc = match.group(2).strip(" :：-")
        label = f"{kind}占位"
        if desc:
            label = f"{label}: {desc}"
        normalized_lines.append(f"[IMAGE_PLACEHOLDER: {label}]")
    return "\n".join(normalized_lines)


def _wrap_latex_document(text: str) -> str:
    docclass = "\\documentclass[11pt,a4paper]{ctexart}"
    preamble = (
        f"{docclass}\n"
        "\\usepackage[margin=1in]{geometry}\n"
        "\\usepackage{amsmath,amssymb,amsthm,mathtools,bm}\n"
        "\\usepackage{graphicx}\n"
        "\\usepackage{booktabs,longtable,array,multirow}\n"
        "\\usepackage{caption}\n"
        "\\usepackage{float}\n"
        "\\usepackage{tikz}\n"
        "\\usepackage{tikz-cd}\n"
        "\\usetikzlibrary{arrows.meta,calc,cd,decorations.pathmorphing,matrix,positioning,shapes.geometric}\n"
        "\\usepackage{hyperref}\n"
        "\\hypersetup{hidelinks}\n"
        "\\setlength{\\parindent}{2em}\n"
        "\\setlength{\\parskip}{0.35em}\n"
        "\\begin{document}\n"
    )
    return preamble + text.rstrip() + "\n\\end{document}\n"

