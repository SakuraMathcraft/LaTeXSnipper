"""Optional Pandoc export backend for LaTeXSnipper."""

from __future__ import annotations

import importlib.util
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from runtime.pandoc_runtime import load_configured_pandoc_path, save_configured_pandoc_path

logger = logging.getLogger(__name__)


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
    needs_file: bool = False


PANDOC_FORMATS: tuple[PandocFormat, ...] = (
    PandocFormat("pandoc_docx", "Word (.docx)", "docx", ".docx", needs_file=True),
    PandocFormat("pandoc_odt", "ODT (.odt)", "odt", ".odt", needs_file=True),
    PandocFormat("pandoc_pptx", "PowerPoint (.pptx)", "pptx", ".pptx", needs_file=True),
    PandocFormat("pandoc_epub", "EPUB (.epub)", "epub", ".epub", needs_file=True),
    PandocFormat("pandoc_pdf", "PDF (.pdf)", "pdf", ".pdf", needs_file=True),
    PandocFormat("pandoc_html_standalone", "HTML 独立页(.html)", "html", ".html"),
    PandocFormat("pandoc_typst", "Typst (.typ)", "typst", ".typ"),
    PandocFormat("pandoc_plain", "纯文本 (.txt)", "plain", ".txt"),
)

PANDOC_FORMAT_MAP: dict[str, PandocFormat] = {f.key: f for f in PANDOC_FORMATS}


_available_cache: bool | None = None
_pandoc_version_cache: str | None = None
_pandoc_path_cache: str | None = None


def _append_to_path_once(directory: Path) -> None:
    path_value = os.environ.get("PATH", "")
    dir_str = str(directory)
    entries = [os.path.normcase(os.path.abspath(item)) for item in path_value.split(os.pathsep) if item]
    key = os.path.normcase(os.path.abspath(dir_str))
    if key not in entries:
        os.environ["PATH"] = dir_str + os.pathsep + path_value


def _find_pandoc_binary() -> str | None:
    configured = load_configured_pandoc_path()
    if configured is not None:
        _append_to_path_once(configured.parent)
        os.environ["PYPANDOC_PANDOC"] = str(configured)
        return str(configured)

    found = shutil.which("pandoc")
    if found:
        os.environ["PYPANDOC_PANDOC"] = found
        return found
    return None


def check_pandoc_available(*, force: bool = False) -> bool:
    global _available_cache, _pandoc_version_cache, _pandoc_path_cache
    if _available_cache is not None and not force:
        return _available_cache

    _available_cache = False
    _pandoc_version_cache = None
    _pandoc_path_cache = None

    if force:
        sys.modules.pop("pypandoc", None)

    if importlib.util.find_spec("pypandoc") is None:
        logger.debug("pypandoc is not installed – Pandoc export disabled")
        return False

    pandoc_path = _find_pandoc_binary()

    if not pandoc_path:
        logger.debug("pandoc binary not found – Pandoc export disabled")
        return False

    try:
        ver_output = subprocess.check_output(
            [pandoc_path, "--version"],
            stderr=subprocess.STDOUT,
            text=True,
            timeout=10,
            **_hidden_subprocess_kwargs(),
        )
        first_line = ver_output.splitlines()[0] if ver_output else ""
        _pandoc_version_cache = first_line.strip()
        _pandoc_path_cache = str(Path(pandoc_path).resolve())
        save_configured_pandoc_path(_pandoc_path_cache)
    except Exception:
        _pandoc_version_cache = "(unknown version)"
        _pandoc_path_cache = str(pandoc_path)

    _available_cache = True
    logger.info("Pandoc available: %s", _pandoc_version_cache)
    return True


def is_available() -> bool:
    return check_pandoc_available()


def _subprocess_flags() -> int:
    if os.name != "nt":
        return 0
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _hidden_subprocess_kwargs() -> dict:
    if os.name != "nt":
        return {}
    kwargs = {"creationflags": _subprocess_flags()}
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        kwargs["startupinfo"] = startupinfo
    except Exception:
        pass
    return kwargs


def _wrap_formula_in_document(latex: str) -> str:
    text = (latex or "").strip()
    if text.startswith("$$") and text.endswith("$$"):
        text = text[2:-2].strip()
    elif text.startswith("$") and text.endswith("$") and "$" not in text[1:-1]:
        text = text[1:-1].strip()

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
    import re
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
    if source.startswith(("\\[", "$$", "\\begin{", "\\frac", "\\sum", "\\int", "\\lim")):
        return True
    if "\\" in source:
        return True
    return any(token in source for token in ("^", "_", "="))


def _ensure_mathjax_script(html: str) -> str:
    if "MathJax" in html or ("math inline" not in html and "math display" not in html):
        return html
    script = (
        '  <script defer=""\n'
        '  src="https://cdn.jsdelivr.net/npm/mathjax@4/tex-chtml.js"\n'
        '  type="text/javascript"></script>\n'
    )
    head_end = html.lower().find("</head>")
    if head_end >= 0:
        return html[:head_end] + script + html[head_end:]
    return script + html


def _read_valid_file_output(path: str, target_key: str) -> bytes | None:
    output_path = Path(path)
    if not output_path.is_file() or output_path.stat().st_size == 0:
        return None
    data = output_path.read_bytes()
    if target_key == "pandoc_pdf" and not data.startswith(b"%PDF-"):
        return None
    return data


def convert_latex_to(
    target_key: str,
    latex: str,
    *,
    as_document: bool = True,
    extra_args: list[str] | None = None,
) -> str | bytes:
    if not is_available():
        raise PandocNotAvailable(
            "Pandoc 导出不可用。"
        )

    fmt = PANDOC_FORMAT_MAP.get(target_key)
    if fmt is None:
        raise ValueError(f"Unknown Pandoc format key: {target_key!r}")

    import pypandoc  # type: ignore[import-untyped]

    is_complete_doc = (latex or "").strip().startswith("\\documentclass")
    has_inline_math = "$" in (latex or "")
    is_text_content = has_inline_math and not is_complete_doc and not (latex or "").strip().startswith("\\[")

    if is_text_content:
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
        if "--mathjax" not in args:
            args.append("--mathjax")

    if target_key == "pandoc_pdf" and "--pdf-engine" not in " ".join(args):
        engine = _find_pdf_engine()
        if engine:
            args.extend(["--pdf-engine", engine])
        else:
            raise PandocConversionError(
                "未找到 LaTeX 引擎，无法导出 PDF。"
            )
        if is_text_content and "--pdf-engine" in args:
            args.extend(_pdf_text_font_args())

    if fmt.needs_file:
        with tempfile.NamedTemporaryFile(
            suffix=fmt.extension, delete=False
        ) as tmp:
            tmp_path = tmp.name
        try:
            pypandoc.convert_text(
                src,
                fmt.pandoc_format,
                format=input_fmt,
                outputfile=tmp_path,
                extra_args=args,
            )
            data = _read_valid_file_output(tmp_path, target_key)
            if data is None:
                raise PandocConversionError(
                    f"Pandoc conversion to {fmt.pandoc_format} produced no output"
                )
            return data
        except Exception as exc:
            data = _read_valid_file_output(tmp_path, target_key)
            if target_key == "pandoc_pdf" and data is not None:
                logger.warning(
                    "Pandoc reported a PDF conversion error after producing a valid PDF: %s",
                    exc,
                )
                return data
            raise PandocConversionError(
                f"Pandoc conversion to {fmt.pandoc_format} failed: {exc}"
            ) from exc
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    else:
        try:
            result = pypandoc.convert_text(
                src,
                fmt.pandoc_format,
                format=input_fmt,
                extra_args=args,
            )
            if target_key == "pandoc_html_standalone":
                result = _ensure_mathjax_script(result)
            return result
        except Exception as exc:
            raise PandocConversionError(
                f"Pandoc conversion to {fmt.pandoc_format} failed: {exc}"
            ) from exc


def get_format_label(key: str) -> str:
    fmt = PANDOC_FORMAT_MAP.get(key)
    return fmt.label if fmt else key
