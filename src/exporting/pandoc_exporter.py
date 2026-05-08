"""Optional Pandoc export backend for LaTeXSnipper.

Uses ``pypandoc`` (pip install pandoc) to convert LaTeX / Markdown / MathML
inputs to docx, odt, epub, rtf, plain-text and other Pandoc-supported formats.

Pandoc is treated as an **optional** dependency:
  * If ``pypandoc`` is not installed *or* the pandoc binary is missing, the
    module exposes ``is_available() -> False`` and every public converter
    raises ``PandocNotAvailable``.
  * The rest of LaTeXSnipper keeps working without Pandoc.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class PandocNotAvailable(RuntimeError):
    """Raised when pypandoc or the pandoc binary cannot be found."""


class PandocConversionError(RuntimeError):
    """Raised when a Pandoc conversion fails."""


# ---------------------------------------------------------------------------
# Format descriptor
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PandocFormat:
    """Metadata for a single Pandoc target format."""

    key: str
    label: str
    pandoc_format: str  # pandoc output format name
    extension: str  # file extension (with dot)
    needs_file: bool = False  # True → pandoc writes to a file (binary output)


# All supported Pandoc target formats.
PANDOC_FORMATS: tuple[PandocFormat, ...] = (
    # --- 文档交换格式（二进制） ---
    PandocFormat("pandoc_docx", "Word (.docx)", "docx", ".docx", needs_file=True),
    PandocFormat("pandoc_odt", "ODT (.odt)", "odt", ".odt", needs_file=True),
    PandocFormat("pandoc_epub", "EPUB (.epub)", "epub", ".epub", needs_file=True),
    PandocFormat("pandoc_icml", "InDesign (.icml)", "icml", ".icml"),
    # --- 标记/文本格式 ---
    PandocFormat("pandoc_rtf", "RTF (.rtf)", "rtf", ".rtf"),
    PandocFormat("pandoc_plain", "纯文本 (.txt)", "plain", ".txt"),
    PandocFormat("pandoc_html_standalone", "HTML 独立页", "html", ".html"),
    PandocFormat("pandoc_latex", "LaTeX (.tex)", "latex", ".tex"),
    PandocFormat("pandoc_typst", "Typst (.typ)", "typst", ".typ"),
    PandocFormat("pandoc_gfm", "GitHub Markdown", "gfm", ".md"),
    PandocFormat("pandoc_commonmark", "CommonMark", "commonmark", ".md"),
    PandocFormat("pandoc_rst", "reStructuredText", "rst", ".rst"),
    PandocFormat("pandoc_mediawiki", "MediaWiki", "mediawiki", ".wiki"),
    PandocFormat("pandoc_dokuwiki", "DokuWiki", "dokuwiki", ".txt"),
    PandocFormat("pandoc_org", "Org-mode", "org", ".org"),
    PandocFormat("pandoc_textile", "Textile", "textile", ".textile"),
    PandocFormat("pandoc_jira", "Jira Wiki", "jira", ".txt"),
    PandocFormat("pandoc_man", "Man Page", "man", ".1"),
)

PANDOC_FORMAT_MAP: dict[str, PandocFormat] = {f.key: f for f in PANDOC_FORMATS}


# ---------------------------------------------------------------------------
# Availability check (cached)
# ---------------------------------------------------------------------------

_available_cache: Optional[bool] = None
_pandoc_version_cache: Optional[str] = None
_download_attempted: bool = False


def _find_pandoc_binary() -> Optional[str]:
    """Try to locate the ``pandoc`` executable — prefers deps/pandoc/ over system PATH."""
    # 1. Check deps/pandoc directory FIRST (dependency wizard puts latest version here)
    try:
        deps_dir = Path.cwd() / "deps" / "pandoc"
        if deps_dir.is_dir():
            for candidate in ("pandoc.exe", "pandoc"):
                deps_pandoc = deps_dir / candidate
                if deps_pandoc.exists() and deps_pandoc.is_file():
                    dir_str = str(deps_pandoc.parent)
                    if dir_str not in os.environ.get("PATH", ""):
                        os.environ["PATH"] = dir_str + os.pathsep + os.environ.get("PATH", "")
                    return str(deps_pandoc)
    except Exception:
        pass
    # 2. Check system PATH (fallback)
    found = shutil.which("pandoc")
    if found:
        return found
    return None


def _try_download_pandoc_binary() -> Optional[str]:
    """Use pypandoc.download_pandoc() to fetch the pandoc binary automatically.

    Returns the path to the downloaded binary, or *None* on failure.
    """
    global _download_attempted
    if _download_attempted:
        return None
    _download_attempted = True
    try:
        import pypandoc  # type: ignore[import-untyped]
        logger.info("pandoc binary not found – attempting auto-download via pypandoc…")
        pypandoc.download_pandoc()
        return pypandoc.get_pandoc_path()
    except Exception as exc:
        logger.debug("pypandoc.download_pandoc() failed: %s", exc)
        return None


def check_pandoc_available(*, force: bool = False) -> bool:
    """Return *True* if ``pypandoc`` can be imported **and** a pandoc binary exists.

    When *force* is ``True`` the cache is bypassed *and* an auto-download of
    the pandoc binary is attempted if it cannot be found.
    """
    global _available_cache, _pandoc_version_cache
    if _available_cache is not None and not force:
        return _available_cache

    _available_cache = False
    _pandoc_version_cache = None

    # When force=True, clear stale import cache so a fresh import succeeds
    # after the user has just installed pypandoc.
    if force:
        sys.modules.pop("pypandoc", None)
        _download_attempted = False  # allow re-download attempt

    # 1. Try pypandoc
    try:
        import pypandoc  # type: ignore[import-untyped]
    except ImportError:
        logger.debug("pypandoc is not installed – Pandoc export disabled")
        return False

    # 2. Try to locate pandoc binary via pypandoc or PATH
    pandoc_path: Optional[str] = None
    try:
        pandoc_path = pypandoc.get_pandoc_path()
    except Exception:
        pandoc_path = _find_pandoc_binary()

    # 3. If still not found, try auto-download (first attempt only)
    if not pandoc_path:
        logger.info("pandoc binary not found on system – trying auto-download")
        pandoc_path = _try_download_pandoc_binary()

    if not pandoc_path:
        logger.debug("pandoc binary not found – Pandoc export disabled")
        return False

    # 4. Get version
    try:
        ver_output = subprocess.check_output(
            [pandoc_path, "--version"],
            stderr=subprocess.STDOUT,
            text=True,
            timeout=10,
            creationflags=_subprocess_flags(),
        )
        first_line = ver_output.splitlines()[0] if ver_output else ""
        _pandoc_version_cache = first_line.strip()
    except Exception:
        _pandoc_version_cache = "(unknown version)"

    _available_cache = True
    logger.info("Pandoc available: %s", _pandoc_version_cache)
    return True


def pandoc_version() -> Optional[str]:
    """Return the pandoc version string, or *None* if unavailable."""
    check_pandoc_available()
    return _pandoc_version_cache


def is_available() -> bool:
    """Convenience alias for ``check_pandoc_available()``."""
    return check_pandoc_available()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _subprocess_flags() -> int:
    if os.name != "nt":
        return 0
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _wrap_formula_in_document(latex: str) -> str:
    """Wrap a single LaTeX formula in a minimal standalone document.

    This is needed because Pandoc expects a *document* rather than a bare
    formula.  Using ``standalone`` class keeps the output compact.
    """
    # Strip outer $ / $$ delimiters if present
    text = (latex or "").strip()
    if text.startswith("$$") and text.endswith("$$"):
        text = text[2:-2].strip()
    elif text.startswith("$") and text.endswith("$"):
        text = text[1:-1].strip()

    return (
        "\\documentclass[preview,border=1pt,varwidth]{standalone}\n"
        "\\usepackage{amsmath,amssymb,amsfonts}\n"
        "\\begin{document}\n"
        f"\\[{text}\\]\n"
        "\\end{document}\n"
    )


def _wrap_markdown_formula(latex: str) -> str:
    """Wrap a formula as a Markdown document with a math block."""
    text = (latex or "").strip()
    if text.startswith("$$") and text.endswith("$$"):
        inner = text[2:-2].strip()
    elif text.startswith("$") and text.endswith("$"):
        inner = text[1:-1].strip()
    else:
        inner = text
    return f"$$\n{inner}\n$$\n"


# ---------------------------------------------------------------------------
# Core conversion
# ---------------------------------------------------------------------------


def convert_latex_to(
    target_key: str,
    latex: str,
    *,
    as_document: bool = True,
    extra_args: list[str] | None = None,
) -> str | bytes:
    """Convert *latex* to the Pandoc format identified by *target_key*.

    Parameters
    ----------
    target_key:
        One of the keys in ``PANDOC_FORMAT_MAP``.
    latex:
        LaTeX source (may be a bare formula or a full document).
    as_document:
        If *True* (default), wraps bare formulas in a minimal LaTeX document
        before conversion.  Set to *False* if *latex* is already a full
        document.
    extra_args:
        Additional CLI arguments passed to pandoc.

    Returns
    -------
    str or bytes
        For text-based formats a ``str`` is returned; for binary formats
        (docx, odt, epub) ``bytes`` are returned.
    """
    if not is_available():
        raise PandocNotAvailable(
            "Pandoc 导出不可用。请安装 pypandoc (pip install pandoc) 并确保 pandoc 可执行文件在 PATH 中。"
        )

    fmt = PANDOC_FORMAT_MAP.get(target_key)
    if fmt is None:
        raise ValueError(f"Unknown Pandoc format key: {target_key!r}")

    import pypandoc  # type: ignore[import-untyped]

    # Prepare source
    if as_document:
        src = _wrap_formula_in_document(latex)
    else:
        src = latex

    args = extra_args or []

    if fmt.needs_file:
        # Binary output → write to a temp file, then read back
        with tempfile.NamedTemporaryFile(
            suffix=fmt.extension, delete=False
        ) as tmp:
            tmp_path = tmp.name
        try:
            pypandoc.convert_text(
                src,
                fmt.pandoc_format,
                format="latex",
                outputfile=tmp_path,
                extra_args=args,
            )
            data = Path(tmp_path).read_bytes()
            return data
        except Exception as exc:
            raise PandocConversionError(
                f"Pandoc conversion to {fmt.pandoc_format} failed: {exc}"
            ) from exc
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    else:
        # Text output
        try:
            result = pypandoc.convert_text(
                src,
                fmt.pandoc_format,
                format="latex",
                extra_args=args,
            )
            return result
        except Exception as exc:
            raise PandocConversionError(
                f"Pandoc conversion to {fmt.pandoc_format} failed: {exc}"
            ) from exc


def convert_markdown_to(
    target_key: str,
    markdown: str,
    *,
    extra_args: list[str] | None = None,
) -> str | bytes:
    """Convert *markdown* (with math blocks) to the Pandoc format *target_key*.

    Similar to :func:`convert_latex_to` but the input format is
    ``markdown+tex_math_dollars``.
    """
    if not is_available():
        raise PandocNotAvailable(
            "Pandoc 导出不可用。请安装 pypandoc (pip install pandoc) 并确保 pandoc 可执行文件在 PATH 中。"
        )

    fmt = PANDOC_FORMAT_MAP.get(target_key)
    if fmt is None:
        raise ValueError(f"Unknown Pandoc format key: {target_key!r}")

    import pypandoc  # type: ignore[import-untyped]

    args = extra_args or []

    if fmt.needs_file:
        with tempfile.NamedTemporaryFile(
            suffix=fmt.extension, delete=False
        ) as tmp:
            tmp_path = tmp.name
        try:
            pypandoc.convert_text(
                markdown,
                fmt.pandoc_format,
                format="markdown+tex_math_dollars",
                outputfile=tmp_path,
                extra_args=args,
            )
            data = Path(tmp_path).read_bytes()
            return data
        except Exception as exc:
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
                markdown,
                fmt.pandoc_format,
                format="markdown+tex_math_dollars",
                extra_args=args,
            )
            return result
        except Exception as exc:
            raise PandocConversionError(
                f"Pandoc conversion to {fmt.pandoc_format} failed: {exc}"
            ) from exc


def get_available_format_keys() -> list[str]:
    """Return keys of all Pandoc formats (always returns the full list;
    availability is checked separately)."""
    return [f.key for f in PANDOC_FORMATS]


def get_format_label(key: str) -> str:
    """Return the human-readable label for a Pandoc format key."""
    fmt = PANDOC_FORMAT_MAP.get(key)
    return fmt.label if fmt else key
