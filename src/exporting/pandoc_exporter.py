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
    """Raised when pypandoc or the pandoc binary cannot be found."""


class PandocConversionError(RuntimeError):
    """Raised when a Pandoc conversion fails."""


@dataclass(frozen=True)
class PandocFormat:
    """Metadata for a single Pandoc target format."""

    key: str
    label: str
    pandoc_format: str  # pandoc output format name
    extension: str  # file extension (with dot)
    needs_file: bool = False  # True when pandoc writes to a file (binary output)


PANDOC_FORMATS: tuple[PandocFormat, ...] = (
    PandocFormat("pandoc_docx", "Word (.docx)", "docx", ".docx", needs_file=True),
    PandocFormat("pandoc_odt", "ODT (.odt)", "odt", ".odt", needs_file=True),
    PandocFormat("pandoc_epub", "EPUB (.epub)", "epub", ".epub", needs_file=True),
    PandocFormat("pandoc_icml", "InDesign (.icml)", "icml", ".icml"),
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
    """Try to locate the ``pandoc`` executable."""
    configured = load_configured_pandoc_path()
    if configured is not None:
        _append_to_path_once(configured.parent)
        os.environ["PYPANDOC_PANDOC"] = str(configured)
        return str(configured)

    try:
        deps_dir = Path.cwd() / "deps" / "pandoc"
        if deps_dir.is_dir():
            for candidate in ("pandoc.exe", "pandoc"):
                deps_pandoc = deps_dir / candidate
                if deps_pandoc.exists() and deps_pandoc.is_file():
                    _append_to_path_once(deps_pandoc.parent)
                    os.environ["PYPANDOC_PANDOC"] = str(deps_pandoc)
                    return str(deps_pandoc)
    except Exception:
        pass
    found = shutil.which("pandoc")
    if found:
        os.environ["PYPANDOC_PANDOC"] = found
        return found
    return None


def check_pandoc_available(*, force: bool = False) -> bool:
    """Return *True* if ``pypandoc`` can be imported **and** a pandoc binary exists.

    When *force* is ``True`` the cache is bypassed. This function never
    downloads or installs pandoc; dependency management owns installation.
    """
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


def pandoc_version() -> str | None:
    """Return the pandoc version string, or *None* if unavailable."""
    check_pandoc_available()
    return _pandoc_version_cache


def pandoc_path() -> str | None:
    """Return the resolved pandoc executable path, or *None* if unavailable."""
    check_pandoc_available()
    return _pandoc_path_cache


def is_available() -> bool:
    """Convenience alias for ``check_pandoc_available()``."""
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
    """Wrap a single LaTeX formula in a minimal standalone document.

    This is needed because Pandoc expects a *document* rather than a bare
    formula.  Using ``standalone`` class keeps the output compact.
    """
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
            "Pandoc 导出不可用。请安装 pypandoc (pip install pypandoc) 并确保 pandoc 可执行文件在 PATH 中。"
        )

    fmt = PANDOC_FORMAT_MAP.get(target_key)
    if fmt is None:
        raise ValueError(f"Unknown Pandoc format key: {target_key!r}")

    import pypandoc  # type: ignore[import-untyped]

    if as_document:
        src = _wrap_formula_in_document(latex)
    else:
        src = latex

    args = extra_args or []

    if fmt.needs_file:
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
            "Pandoc 导出不可用。请安装 pypandoc (pip install pypandoc) 并确保 pandoc 可执行文件在 PATH 中。"
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
