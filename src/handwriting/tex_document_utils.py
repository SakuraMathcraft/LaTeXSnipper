from __future__ import annotations

import re


WRAP_ENVIRONMENTS = {
    "行内公式 $...$": ("inline", "$", "$"),
    "行间公式 \\[...\\]": ("display", r"\[", r"\]"),
    "equation": ("equation", r"\begin{equation}", r"\end{equation}"),
    "equation*": ("equation*", r"\begin{equation*}", r"\end{equation*}"),
    "align": ("align", r"\begin{align}", r"\end{align}"),
    "align*": ("align*", r"\begin{align*}", r"\end{align*}"),
    "multline": ("multline", r"\begin{multline}", r"\end{multline}"),
    "multline*": ("multline*", r"\begin{multline*}", r"\end{multline*}"),
}


def sanitize_tex_templates(text: str) -> str:
    value = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not value:
        return ""
    value = re.sub(r"\\placeholder\{([^{}]*)\}", r" {\1} ", value)
    value = re.sub(r"(?<!\\)placeholder\{([^{}]*)\}", r" {\1} ", value)
    value = re.sub(r"_\{\}", "", value)
    value = re.sub(r"\^\{\}", "", value)
    value = re.sub(r"\\!\s*\\mathrm\{d\}", r"\\,\\mathrm{d}", value)
    value = re.sub(r"[ \t]{2,}", " ", value)
    value = re.sub(r"[ \t]+\n", "\n", value)
    return value.rstrip()


def looks_like_naked_formula_line(text: str) -> bool:
    stripped = str(text or "").strip()
    if not stripped or stripped.startswith("%"):
        return False
    if re.search(r"\$[^$]+\$", stripped) or re.search(r"\\\([^)]*\\\)", stripped):
        return False
    if stripped.startswith("$") and stripped.endswith("$"):
        return False
    if any(token in stripped for token in (r"\[", r"\]", "$$", r"\(", r"\)")):
        return False
    if any(
        stripped.startswith(prefix)
        for prefix in (
            "#",
            "-",
            "*",
            r"\item",
            r"\section",
            r"\subsection",
            r"\paragraph",
            r"\chapter",
            r"\documentclass",
            r"\usepackage",
            r"\geometry",
            r"\title",
            r"\author",
            r"\date",
        )
    ):
        return False
    has_math_marker = bool(re.search(r"(\\[A-Za-z]+|[_^=<>]|[+\-*/]|[{}])", stripped))
    if not has_math_marker:
        return False
    plain_words = re.findall(r"[A-Za-z]{3,}", stripped)
    if plain_words and not re.search(r"\\[A-Za-z]+|[_^=<>]", stripped):
        return False
    return True


def normalize_document_body(text: str) -> str:
    lines = str(text or "").splitlines()
    normalized: list[str] = []
    in_math_block = False
    for raw_line in lines:
        line = sanitize_tex_templates(raw_line.rstrip())
        stripped = line.strip()
        if stripped.startswith(r"\[") or stripped.startswith("$$") or stripped.startswith(r"\begin{"):
            in_math_block = True
            normalized.append(line)
            continue
        if stripped.startswith(r"\]") or stripped.endswith("$$") or stripped.startswith(r"\end{"):
            normalized.append(line)
            in_math_block = False
            continue
        if in_math_block or not looks_like_naked_formula_line(stripped):
            normalized.append(line)
            continue
        normalized.extend([r"\[", stripped, r"\]"])
    return "\n".join(normalized).strip()


def wrap_tex_document(text: str) -> str:
    content = sanitize_tex_templates(str(text or "")).strip()
    if not content:
        return ""
    if "\\documentclass" in content and "\\begin{document}" in content and "\\end{document}" in content:
        begin_idx = content.find("\\begin{document}")
        end_idx = content.rfind("\\end{document}")
        if begin_idx >= 0 and end_idx > begin_idx:
            begin_token = "\\begin{document}"
            preamble = content[: begin_idx + len(begin_token)].rstrip()
            body = content[begin_idx + len(begin_token): end_idx].strip()
            normalized_body = normalize_document_body(body) or "% TODO: 补全文档正文"
            suffix = content[end_idx:].strip()
            return f"{preamble}\n{normalized_body}\n{suffix}".strip()
        return content

    if "\\documentclass" in content:
        if "\\begin{document}" in content and "\\end{document}" not in content:
            return content + "\n\\end{document}"
        if "\\begin{document}" not in content:
            lines = content.splitlines()
            preamble_lines: list[str] = []
            body_lines: list[str] = []
            in_preamble = True
            for line in lines:
                stripped = line.strip()
                if in_preamble and (
                    not stripped
                    or stripped.startswith("%")
                    or stripped.startswith("\\documentclass")
                    or stripped.startswith("\\usepackage")
                    or stripped.startswith("\\geometry")
                    or stripped.startswith("\\set")
                    or stripped.startswith("\\title")
                    or stripped.startswith("\\author")
                    or stripped.startswith("\\date")
                    or stripped.startswith("\\new")
                ):
                    preamble_lines.append(line)
                else:
                    in_preamble = False
                    body_lines.append(line)
            preamble = "\n".join(preamble_lines).strip()
            body = normalize_document_body("\n".join(body_lines)) or "% TODO: 补全文档正文"
            return f"{preamble}\n\n\\begin{{document}}\n{body}\n\\end{{document}}".strip()
        return content

    content = normalize_document_body(content)
    return (
        "\\documentclass[UTF8]{ctexart}\n"
        "\\usepackage{amsmath,amssymb,amsthm,mathtools,bm}\n"
        "\\usepackage{geometry}\n"
        "\\usepackage{graphicx}\n"
        "\\usepackage{booktabs}\n"
        "\\usepackage{array}\n"
        "\\usepackage{multirow}\n"
        "\\geometry{a4paper,margin=2.2cm}\n\n"
        "\\begin{document}\n"
        f"{content}\n"
        "\\end{document}"
    )


def validate_tex_document(text: str) -> str | None:
    content = str(text or "")
    if not content.strip():
        return "没有可编译的 TeX 文档。"
    if "placeholder{}" in content or "\\placeholder{}" in content:
        return "文档中仍有未填写的模板占位符，请先补全后再编译。"
    return None


# ---------------------------------------------------------------------------
# LaTeX document → Typst document conversion
# ---------------------------------------------------------------------------

# Patterns for LaTeX math environments that need conversion
_LATEX_DISPLAY_MATH_RE = re.compile(
    r'(?<!\\)\$\$\s*(.+?)\s*(?<!\\)\$\$',
    re.DOTALL,
)
_LATEX_INLINE_MATH_RE = re.compile(
    r'(?<!\\)\$\s*(.+?)\s*(?<!\\)\$',
)
_LATEX_DISPLAY_BRACKET_RE = re.compile(
    r'(?<!\\)\\\[\s*(.+?)\s*(?<!\\)\\\]',
    re.DOTALL,
)
_LATEX_ENV_RE = re.compile(
    r'\\begin\{(equation\*?|align\*?|multline\*?|gather\*?)\}\s*(.+?)\s*\\end\{\1\}',
    re.DOTALL,
)

# Typst document template.
# Uses Typst's default A4 page size (matching LaTeX a4paper) for PDF output.
# Note: width:auto/height:auto only work for SVG, not PDF.
_TYPST_DOC_TEMPLATE = """\
#set page(margin: (x: 2.2cm, y: 2.2cm))
#set text(font: ("Noto Sans CJK SC", "Source Han Sans SC", "Microsoft YaHei", "SimHei", "Noto Sans", "Helvetica"), size: 12pt)
#set par(leading: 0.6em, justify: true)

#show math.equation: set text(size: 12pt)

{body}\
"""


def convert_latex_doc_to_typst_doc(latex_doc: str) -> str:
    """Convert a full LaTeX document to a Typst document.

    Extracts the document body (between ``\\begin{document}`` and
    ``\\end{document}``), converts LaTeX math formulas to Typst math
    syntax, and wraps the result in a clean Typst document template.

    Falls back to the raw body text wrapped in a Typst template if
    pypandoc is unavailable.
    """
    content = str(latex_doc or "").strip()
    if not content:
        return _TYPST_DOC_TEMPLATE.format(body="")

    # Extract body from LaTeX document
    body = _extract_latex_body(content)

    # Convert math formulas from LaTeX to Typst
    body = _convert_body_math_to_typst(body)

    return _TYPST_DOC_TEMPLATE.format(body=body)


def _extract_latex_body(latex_doc: str) -> str:
    """Extract the document body from a LaTeX document string."""
    begin_marker = "\\begin{document}"
    end_marker = "\\end{document}"

    begin_idx = latex_doc.find(begin_marker)
    if begin_idx >= 0:
        body_start = begin_idx + len(begin_marker)
        end_idx = latex_doc.find(end_marker, body_start)
        if end_idx >= 0:
            return latex_doc[body_start:end_idx].strip()

    # No document environment found - treat entire content as body,
    # but strip preamble commands
    return _strip_latex_preamble(latex_doc)


def _strip_latex_preamble(text: str) -> str:
    """Strip LaTeX preamble commands, keeping only body content."""
    lines = text.splitlines()
    body_lines: list[str] = []
    in_preamble = True
    for line in lines:
        stripped = line.strip()
        if in_preamble and (
            not stripped
            or stripped.startswith("%")
            or stripped.startswith("\\documentclass")
            or stripped.startswith("\\usepackage")
            or stripped.startswith("\\geometry")
            or stripped.startswith("\\set")
            or stripped.startswith("\\title")
            or stripped.startswith("\\author")
            or stripped.startswith("\\date")
            or stripped.startswith("\\new")
            or stripped.startswith("\\Declare")
            or stripped.startswith("\\makeatletter")
            or stripped.startswith("\\makeatother")
        ):
            continue
        in_preamble = False
        body_lines.append(line)
    return "\n".join(body_lines).strip()


def _convert_body_math_to_typst(body: str) -> str:
    """Convert LaTeX math formulas in document body to Typst math syntax."""
    try:
        from core.mathcraft_document_engine import convert_latex_to_typst as _formula_to_typst
    except ImportError:
        return body

    text = body

    # Order matters: handle environments before display/inline math
    # to avoid double-processing nested content.

    # 1. Convert \begin{equation}...\end{equation} etc.
    def _env_replacer(m: re.Match) -> str:
        inner = m.group(2).strip()
        converted = _formula_to_typst(inner)
        # Typst uses $ ... $ for display math equations
        if converted:
            return f"$ {converted} $"
        return m.group(0)

    text = _LATEX_ENV_RE.sub(_env_replacer, text)

    # 2. Convert $$...$$ display math
    def _display_math_replacer(m: re.Match) -> str:
        inner = m.group(1).strip()
        converted = _formula_to_typst(inner)
        if converted:
            return f"$ {converted} $"
        return m.group(0)

    text = _LATEX_DISPLAY_MATH_RE.sub(_display_math_replacer, text)

    # 3. Convert \[...\] display math
    text = _LATEX_DISPLAY_BRACKET_RE.sub(_display_math_replacer, text)

    # 4. Convert $...$ inline math
    def _inline_math_replacer(m: re.Match) -> str:
        inner = m.group(1).strip()
        # Skip if it looks like a currency amount
        if re.match(r'^[\d,.]+$', inner):
            return m.group(0)
        converted = _formula_to_typst(inner)
        if converted:
            return f"$ {converted} $"
        return m.group(0)

    text = _LATEX_INLINE_MATH_RE.sub(_inline_math_replacer, text)

    return text
