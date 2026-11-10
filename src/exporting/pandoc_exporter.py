"""Optional Pandoc export backend for LaTeXSnipper."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from exporting.formula_format_helpers import normalize_latex_for_export
from localization.manager import mark_for_translation
from rendering.mathjax_runtime import cdn_loader_script, cdn_root
from runtime.pandoc_runtime import resolve_pandoc
from runtime.processes import hidden_subprocess_kwargs, independent_process_environment

logger = logging.getLogger(f"latexsnipper.{__name__}")


class PandocNotAvailable(RuntimeError):
    pass


class PandocConversionError(RuntimeError):
    pass


@dataclass(frozen=True)
class PandocFormat:
    key: str
    label: str
    pandoc_format: str
    extension: str
    # Pandoc requires a temporary output path for binary writers.
    # All formats are saved as files by the UI, including its text writers.
    requires_output_file: bool = False


PANDOC_FORMATS: tuple[PandocFormat, ...] = (
    PandocFormat(
        "pandoc_docx", "Word (.docx)", "docx", ".docx", requires_output_file=True
    ),
    PandocFormat("pandoc_odt", "ODT (.odt)", "odt", ".odt", requires_output_file=True),
    PandocFormat(
        "pandoc_pptx", "PowerPoint (.pptx)", "pptx", ".pptx", requires_output_file=True
    ),
    PandocFormat(
        "pandoc_epub", "EPUB (.epub)", "epub", ".epub", requires_output_file=True
    ),
    PandocFormat("pandoc_pdf", "PDF (.pdf)", "pdf", ".pdf", requires_output_file=True),
    PandocFormat(
        "pandoc_html_standalone",
        mark_for_translation("HTML 独立页(.html)"),
        "html",
        ".html",
    ),
    PandocFormat("pandoc_typst", "Typst (.typ)", "typst", ".typ"),
    PandocFormat(
        "pandoc_plain", mark_for_translation("纯文本 (.txt)"), "plain", ".txt"
    ),
)

PANDOC_FORMAT_MAP: dict[str, PandocFormat] = {f.key: f for f in PANDOC_FORMATS}


def is_available() -> bool:
    if resolve_pandoc() is None:
        logger.debug("Pandoc was not found on PATH")
        return False
    return True


def _wrap_formula_in_document(latex: str) -> str:
    text = normalize_latex_for_export(latex)

    has_inline_math = "$" in text and not text.startswith("\\[")

    if has_inline_math:
        return (
            "\\documentclass[preview,border=1pt,varwidth]{standalone}\n"
            "\\usepackage{amsmath,amssymb,amsfonts}\n"
            "\\begin{document}\n"
            f"{text}\n"
            "\\end{document}\n"
        )

    return (
        "\\documentclass[preview,border=1pt,varwidth]{standalone}\n"
        "\\usepackage{amsmath,amssymb,amsfonts}\n"
        "\\begin{document}\n"
        f"\\[{text}\\]\n"
        "\\end{document}\n"
    )


def _find_pdf_engine() -> str | None:
    for engine in ("xelatex", "lualatex", "pdflatex"):
        if shutil.which(engine):
            return engine
    return None


def _pdf_text_font_args() -> list[str]:
    if os.name == "nt":
        main_font = "Times New Roman"
        cjk_font = "SimSun"
    elif sys.platform == "darwin":
        main_font = "Times New Roman"
        cjk_font = "Songti SC"
    else:
        main_font = "TeX Gyre Termes"
        cjk_font = "Noto Serif CJK SC"
    return ["-V", f"mainfont={main_font}", "-V", f"CJKmainfont={cjk_font}"]


def _preprocess_for_pptx(text: str) -> str:
    lines = text.split("\n")
    result = []
    for line in lines:
        if re.match(r"^\s*---\s*$", line):
            result.append("")
            result.append("##")
            result.append("")
        else:
            result.append(line)
    return "\n".join(result)


def _looks_like_latex_formula(text: str) -> bool:
    source = text.strip()
    if not source:
        return False
    if source.startswith(
        ("\\[", "$$", "\\begin{", "\\frac", "\\sum", "\\int", "\\lim")
    ):
        return True
    if "\\" in source:
        return True
    return any(token in source for token in ("^", "_", "="))


def _ensure_mathjax_script(html: str) -> str:
    # Pandoc preserves TeX in the page; replace its generated loader with our
    # pinned configuration, retaining browser-side typesetting of that source.
    entry = cdn_root() + "/startup.js"
    pattern = (
        r"<script\b[^>]*\bsrc=[\"\']" + re.escape(entry) + r"[\"\'][^>]*>\s*</script>"
    )
    html, count = re.subn(pattern, "", html, flags=re.IGNORECASE)
    if not count and "math inline" not in html and "math display" not in html:
        return html
    script = cdn_loader_script()
    head_end = html.lower().find("</head>")
    return (
        html[:head_end] + script + html[head_end:] if head_end >= 0 else script + html
    )


def _read_valid_file_output(path: Path, target_key: str) -> bytes | None:
    if not path.is_file() or path.stat().st_size == 0:
        return None
    data = path.read_bytes()
    if target_key == "pandoc_pdf" and not data.startswith(b"%PDF-"):
        return None
    return data


def _run_pandoc(command: list[str], source: str) -> str:
    try:
        result = subprocess.run(
            command,
            input=source.encode("utf-8"),
            capture_output=True,
            env=independent_process_environment(),
            **hidden_subprocess_kwargs(),
        )
        detail = result.stderr.decode("utf-8").strip()
        if result.returncode:
            raise PandocConversionError(
                f"Pandoc exited with code {result.returncode}: {detail}"
            )
        if detail:
            logger.debug("Pandoc: %s", detail)
        return result.stdout.decode("utf-8")
    except FileNotFoundError as exc:
        raise PandocNotAvailable("Pandoc executable is unavailable") from exc
    except (OSError, UnicodeError) as exc:
        raise PandocConversionError(f"Could not run Pandoc: {exc}") from exc


def convert_latex_to(
    target_key: str,
    latex: str,
    *,
    as_document: bool = True,
    extra_args: list[str] | None = None,
    input_format: str | None = None,
) -> str | bytes:
    fmt = PANDOC_FORMAT_MAP.get(target_key)
    if fmt is None:
        raise ValueError(f"Unknown Pandoc format key: {target_key!r}")
    pandoc = resolve_pandoc()
    if pandoc is None:
        raise PandocNotAvailable("Pandoc was not found on PATH")

    is_complete_doc = (latex or "").strip().startswith("\\documentclass")
    has_inline_math = "$" in (latex or "")
    is_text_content = (
        has_inline_math
        and not is_complete_doc
        and not (latex or "").strip().startswith("\\[")
    )

    if input_format is not None:
        src = (latex or "").strip()
        if target_key == "pandoc_pptx":
            src = _preprocess_for_pptx(src)
        input_fmt = input_format
        is_text_content = input_format.startswith("markdown")
    elif is_text_content:
        src = latex.strip()
        if target_key == "pandoc_pptx":
            src = _preprocess_for_pptx(src)
        input_fmt = "markdown+tex_math_dollars"
    elif as_document and not is_complete_doc:
        if _looks_like_latex_formula(latex):
            src = _wrap_formula_in_document(latex)
            input_fmt = "latex"
        else:
            src = (latex or "").strip()
            if target_key == "pandoc_pptx":
                src = _preprocess_for_pptx(src)
            input_fmt = "markdown+tex_math_dollars"
    else:
        src = latex
        input_fmt = "latex"

    args = list(extra_args or [])

    if target_key == "pandoc_pptx" and "--slide-level" not in " ".join(args):
        args.extend(["--slide-level", "2"])

    if target_key == "pandoc_html_standalone":
        if "--standalone" not in args:
            args.append("--standalone")
        args = [
            arg
            for arg in args
            if arg != "--mathjax" and not arg.startswith("--mathjax=")
        ]
        args.append("--mathjax=" + cdn_root() + "/startup.js")

    if target_key == "pandoc_pdf" and "--pdf-engine" not in " ".join(args):
        engine = _find_pdf_engine()
        if engine:
            args.extend(["--pdf-engine", engine])
        else:
            raise PandocConversionError("未找到 LaTeX 引擎，无法导出 PDF。")
        if is_text_content and "--pdf-engine" in args:
            args.extend(_pdf_text_font_args())

    command = [str(pandoc), f"--from={input_fmt}", f"--to={fmt.pandoc_format}", *args]
    if not fmt.requires_output_file:
        result = _run_pandoc(command, src)
        return (
            _ensure_mathjax_script(result)
            if target_key == "pandoc_html_standalone"
            else result
        )

    with tempfile.TemporaryDirectory(prefix="latexsnipper-pandoc-") as temp:
        output = Path(temp) / f"export{fmt.extension}"
        try:
            _run_pandoc([*command, f"--output={output}"], src)
        except PandocConversionError as exc:
            if (
                target_key != "pandoc_pdf"
                or (data := _read_valid_file_output(output, target_key)) is None
            ):
                raise
            logger.warning("Pandoc 报告转换错误，但已生成有效 PDF: %s", exc)
            return data
        data = _read_valid_file_output(output, target_key)
        if data is None:
            raise PandocConversionError(
                f"Pandoc conversion to {fmt.pandoc_format} produced no output"
            )
        return data
