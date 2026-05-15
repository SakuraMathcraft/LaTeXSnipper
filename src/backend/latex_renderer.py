"""LaTeX rendering helpers for pdflatex, xelatex, Typst, and MathJax fallback modes."""

import subprocess
import tempfile
import shutil
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Tuple
import json

try:
    import pypandoc
except ImportError:  # pragma: no cover
    pypandoc = None


@dataclass
class LaTeXCompileResult:
    pdf_path: Optional[Path]
    summary: str = ""
    log_text: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    return_code: Optional[int] = None
    engine: str = ""
    generated_pdf: bool = False
    timed_out: bool = False
    log_path: Optional[Path] = None


def _hidden_subprocess_kwargs() -> dict:
    if os.name != "nt":
        return {}
    kwargs = {
        "creationflags": int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
    }
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        kwargs["startupinfo"] = startupinfo
    except Exception:
        pass
    return kwargs


def _is_command_available(command: str) -> bool:
    try:
        result = subprocess.run(
            [command, "--version"],
            capture_output=True,
            timeout=3,
            text=True,
            **_hidden_subprocess_kwargs(),
        )
        return result.returncode == 0
    except Exception:
        return False


def _normalize_latex_command_path(command: str) -> Optional[str]:
    candidate = str(command or "").strip()
    if not candidate:
        return None
    path = Path(candidate)
    if path.exists():
        return str(path)
    resolved = shutil.which(candidate)
    if resolved:
        return resolved
    return None


def _resolve_latex_command_for_mode(mode: str, latex_path: Optional[str]) -> Optional[str]:
    preferred_name = "xelatex" if mode == "latex_xelatex" else "pdflatex"
    suffix = ".exe" if os.name == "nt" else ""
    candidates = []

    normalized_path = _normalize_latex_command_path(latex_path or "")
    if normalized_path:
        path_obj = Path(normalized_path)
        sibling = path_obj.with_name(preferred_name + path_obj.suffix)
        candidates.append(str(sibling))
        candidates.append(normalized_path)

    candidates.append(preferred_name + suffix)
    candidates.append(preferred_name)

    seen = set()
    for candidate in candidates:
        normalized = _normalize_latex_command_path(candidate)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        if _is_command_available(normalized):
            return normalized
    return None


def _resolve_synctex_command_for_latex(latex_cmd: Optional[str]) -> Optional[str]:
    candidate = _normalize_latex_command_path("synctex")
    if candidate and _is_command_available(candidate):
        return candidate
    normalized = _normalize_latex_command_path(latex_cmd or "")
    if normalized:
        path_obj = Path(normalized)
        sibling = path_obj.with_name("synctex" + path_obj.suffix)
        sibling_cmd = _normalize_latex_command_path(str(sibling))
        if sibling_cmd and _is_command_available(sibling_cmd):
            return sibling_cmd
    return None


def is_supported_document_render_mode(mode: Optional[str]) -> bool:
    return str(mode or "").strip() in {"latex_pdflatex", "latex_xelatex", "typst"}


def get_document_render_mode() -> str:
    return _latex_settings.get_render_mode() if _latex_settings else "auto"


def _extract_latex_error_message(log_text: str, tex_file: Path) -> str:
    lines = [line.rstrip() for line in str(log_text or "").splitlines()]
    tex_name = tex_file.name
    tex_path = str(tex_file)

    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("! "):
            detail = [stripped]
            for extra in lines[index + 1:index + 4]:
                extra_stripped = extra.strip()
                if extra_stripped:
                    detail.append(extra_stripped)
                if extra_stripped.startswith("l.") or extra_stripped.startswith(tex_name) or extra_stripped.startswith(tex_path):
                    break
            return " | ".join(detail)
        if tex_name in stripped or tex_path in stripped:
            if ": error:" in stripped.lower() or re.search(r":\d+:", stripped):
                detail = [stripped]
                for extra in lines[index + 1:index + 3]:
                    extra_stripped = extra.strip()
                    if extra_stripped and not extra_stripped.startswith("This is "):
                        detail.append(extra_stripped)
                return " | ".join(detail)

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("This is "):
            return stripped[:320]
    return ""


def _extract_latex_errors(log_text: str, tex_file: Path) -> list[str]:
    lines = [line.rstrip() for line in str(log_text or "").splitlines()]
    tex_name = tex_file.name
    tex_path = str(tex_file)
    errors = []

    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("! "):
            detail = [stripped]
            for extra in lines[index + 1:index + 4]:
                extra_stripped = extra.strip()
                if extra_stripped:
                    detail.append(extra_stripped)
                if extra_stripped.startswith("l.") or extra_stripped.startswith(tex_name) or extra_stripped.startswith(tex_path):
                    break
            errors.append(" | ".join(detail))
            continue
        if tex_name in stripped or tex_path in stripped:
            if ": error:" in stripped.lower() or re.search(r":\d+:", stripped):
                detail = [stripped]
                for extra in lines[index + 1:index + 3]:
                    extra_stripped = extra.strip()
                    if extra_stripped and not extra_stripped.startswith("This is "):
                        detail.append(extra_stripped)
                errors.append(" | ".join(detail))

    seen = set()
    compact = []
    for item in errors:
        cleaned = re.sub(r"\s+", " ", item).strip()[:400]
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            compact.append(cleaned)
    return compact


def _extract_latex_warnings(log_text: str) -> list[str]:
    warnings = []
    for raw_line in str(log_text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lower = line.lower()
        if "warning" not in lower:
            continue
        if lower.startswith("this is "):
            continue
        cleaned = re.sub(r"\s+", " ", line).strip()[:300]
        if cleaned:
            warnings.append(cleaned)

    seen = set()
    unique = []
    for item in warnings:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def _read_compile_log_file(log_file: Path) -> str:
    try:
        if log_file.exists():
            return log_file.read_text(encoding="utf-8", errors="replace")
    except Exception:
        pass
    return ""


def _merge_compile_logs(stdout_text: str, stderr_text: str, file_log_text: str) -> str:
    parts = []
    if stdout_text:
        parts.append(stdout_text.strip())
    if stderr_text:
        parts.append(stderr_text.strip())
    if file_log_text:
        file_log = file_log_text.strip()
        if file_log and file_log not in "\n\n".join(parts):
            parts.append(file_log)
    return "\n\n".join(part for part in parts if part)


def compile_tex_document_detailed(
    tex_content: str,
    output_dir: Path,
    jobname: str = "document_preview",
    timeout: int = 25,
) -> LaTeXCompileResult:
    mode = get_document_render_mode()
    if not is_supported_document_render_mode(mode):
        return LaTeXCompileResult(
            pdf_path=None,
            summary="请先在设置中选择 LaTeX + pdflatex 或 LaTeX + xelatex。",
        )

    latex_path = _latex_settings.get_latex_path() if _latex_settings else None
    latex_cmd = _resolve_latex_command_for_mode(mode, latex_path)
    engine_name = "xelatex" if mode == "latex_xelatex" else "pdflatex"
    if not latex_cmd:
        return LaTeXCompileResult(
            pdf_path=None,
            summary=f"未找到可用的 {engine_name}，请先在设置中完成 LaTeX 路径配置。",
            engine=engine_name,
        )

    text = str(tex_content or "").strip()
    if not text:
        return LaTeXCompileResult(
            pdf_path=None,
            summary="当前没有可编译的 TeX 文档内容。",
            engine=engine_name,
        )

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    tex_file = output_path / f"{jobname}.tex"
    pdf_file = output_path / f"{jobname}.pdf"
    log_file = output_path / f"{jobname}.log"
    tex_file.write_text(text, encoding="utf-8")

    try:
        result = subprocess.run(
            [
                latex_cmd,
                "-interaction=nonstopmode",
                "-file-line-error",
                "-synctex=1",
                "-output-directory",
                str(output_path),
                str(tex_file),
            ],
            capture_output=True,
            timeout=timeout,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(output_path),
            **_hidden_subprocess_kwargs(),
        )
        file_log_text = _read_compile_log_file(log_file)
        log_text = _merge_compile_logs(result.stdout, result.stderr, file_log_text)
        errors = _extract_latex_errors(log_text, tex_file)
        warnings = _extract_latex_warnings(log_text)
        generated_pdf = pdf_file.exists()
        if generated_pdf and errors:
            summary = "编译存在错误，已尽量生成 PDF。请查看下方编译日志。"
        elif generated_pdf and warnings:
            summary = "编译完成，但存在警告；请查看下方编译日志。"
        elif generated_pdf:
            summary = ""
        else:
            cleaned = _extract_latex_error_message(log_text, tex_file)
            if cleaned:
                cleaned = re.sub(r"\s+", " ", cleaned).strip()[:320]
            summary = cleaned or "TeX 文档编译失败，请检查源码和 LaTeX 环境。"
        return LaTeXCompileResult(
            pdf_path=pdf_file if generated_pdf else None,
            summary=summary,
            log_text=log_text,
            errors=errors,
            warnings=warnings,
            return_code=int(result.returncode),
            engine=engine_name,
            generated_pdf=generated_pdf,
            log_path=log_file if log_file.exists() else None,
        )
    except subprocess.TimeoutExpired as exc:
        file_log_text = _read_compile_log_file(log_file)
        log_text = _merge_compile_logs(
            getattr(exc, "stdout", "") or "",
            getattr(exc, "stderr", "") or "",
            file_log_text,
        )
        return LaTeXCompileResult(
            pdf_path=pdf_file if pdf_file.exists() else None,
            summary="TeX 文档编译超时，请检查内容或 LaTeX 环境。",
            log_text=log_text,
            errors=_extract_latex_errors(log_text, tex_file),
            warnings=_extract_latex_warnings(log_text),
            engine=engine_name,
            generated_pdf=pdf_file.exists(),
            timed_out=True,
            log_path=log_file if log_file.exists() else None,
        )
    except Exception as exc:
        return LaTeXCompileResult(
            pdf_path=None,
            summary=f"TeX 文档编译失败: {exc}",
            engine=engine_name,
            log_path=log_file if log_file.exists() else None,
        )


def synctex_edit_from_pdf(
    *,
    pdf_file: Path,
    page: int,
    x_pt: float,
    y_pt: float,
) -> Tuple[Optional[Path], Optional[int], str]:
    mode = get_document_render_mode()
    if not is_supported_document_render_mode(mode):
        return None, None, "当前渲染引擎不支持 SyncTeX。"
    latex_path = _latex_settings.get_latex_path() if _latex_settings else None
    latex_cmd = _resolve_latex_command_for_mode(mode, latex_path)
    synctex_cmd = _resolve_synctex_command_for_latex(latex_cmd)
    if not synctex_cmd:
        return None, None, "未找到可用的 synctex 命令。"
    target_pdf = Path(pdf_file)
    if not target_pdf.exists():
        return None, None, "PDF 预览文件不存在。"
    try:
        result = subprocess.run(
            [
                synctex_cmd,
                "edit",
                "-o",
                f"{max(1, int(page))}:{float(x_pt):.4f}:{float(y_pt):.4f}:{str(target_pdf)}",
            ],
            capture_output=True,
            timeout=10,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(target_pdf.parent),
            **_hidden_subprocess_kwargs(),
        )
    except Exception as exc:
        return None, None, f"SyncTeX 查询失败: {exc}"

    output = "\n".join(filter(None, [result.stdout, result.stderr]))
    input_match = re.search(r"^Input:(.+)$", output, re.MULTILINE)
    line_match = re.search(r"^Line:(\d+)$", output, re.MULTILINE)
    if not input_match or not line_match:
        cleaned = re.sub(r"\s+", " ", output).strip()
        return None, None, cleaned or "未能从 SyncTeX 输出中解析源码位置。"
    source = Path(input_match.group(1).strip())
    try:
        line_no = int(line_match.group(1))
    except Exception:
        line_no = None
    return source, line_no, ""


def synctex_view_from_source(
    *,
    source_file: Path,
    line_no: int,
    pdf_file: Path,
) -> Tuple[Optional[int], Optional[float], Optional[float], Optional[float], Optional[float], str]:
    mode = get_document_render_mode()
    if not is_supported_document_render_mode(mode):
        return None, None, None, None, None, "当前渲染引擎不支持 SyncTeX。"
    latex_path = _latex_settings.get_latex_path() if _latex_settings else None
    latex_cmd = _resolve_latex_command_for_mode(mode, latex_path)
    synctex_cmd = _resolve_synctex_command_for_latex(latex_cmd)
    if not synctex_cmd:
        return None, None, None, None, None, "未找到可用的 synctex 命令。"
    src = Path(source_file)
    target_pdf = Path(pdf_file)
    if not src.exists():
        return None, None, None, None, None, "源码文件不存在。"
    if not target_pdf.exists():
        return None, None, None, None, None, "PDF 预览文件不存在。"
    try:
        result = subprocess.run(
            [
                synctex_cmd,
                "view",
                "-i",
                f"{max(1, int(line_no))}:1:{str(src)}",
                "-o",
                str(target_pdf),
            ],
            capture_output=True,
            timeout=10,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(target_pdf.parent),
            **_hidden_subprocess_kwargs(),
        )
    except Exception as exc:
        return None, None, None, None, None, f"SyncTeX 查询失败: {exc}"

    output = "\n".join(filter(None, [result.stdout, result.stderr]))
    page_match = re.search(r"^Page:(\d+)$", output, re.MULTILINE | re.IGNORECASE)
    x_match = re.search(r"^x:([+-]?[0-9]*\.?[0-9]+)$", output, re.MULTILINE | re.IGNORECASE)
    y_match = re.search(r"^y:([+-]?[0-9]*\.?[0-9]+)$", output, re.MULTILINE | re.IGNORECASE)
    w_match = re.search(r"^W:([+-]?[0-9]*\.?[0-9]+)$", output, re.MULTILINE | re.IGNORECASE)
    h_match = re.search(r"^H:([+-]?[0-9]*\.?[0-9]+)$", output, re.MULTILINE | re.IGNORECASE)
    if not page_match or not x_match or not y_match:
        cleaned = re.sub(r"\s+", " ", output).strip()
        return None, None, None, None, None, cleaned or "未能从 SyncTeX 输出中解析 PDF 坐标。"
    try:
        page = int(page_match.group(1))
        x_pt = float(x_match.group(1))
        y_pt = float(y_match.group(1))
        w_pt = abs(float(w_match.group(1))) if w_match else None
        h_pt = abs(float(h_match.group(1))) if h_match else None
    except Exception:
        return None, None, None, None, None, "SyncTeX 输出解析失败。"
    return page, x_pt, y_pt, w_pt, h_pt, ""


class LaTeXRenderer:
    """Render individual LaTeX formulas to SVG."""

    def __init__(self, latex_cmd: Optional[str] = None):
        self.latex_cmd = latex_cmd
        self._validate_latex()

    def _validate_latex(self):
        """Validate the configured LaTeX executable."""
        if self.latex_cmd is None:
            self.latex_cmd = self._detect_latex()

        if self.latex_cmd and not Path(self.latex_cmd).exists():
            print(f"[WARN] LaTeX path does not exist: {self.latex_cmd}")
            self.latex_cmd = None

    def _detect_latex(self) -> Optional[str]:
        """Detect pdflatex or xelatex from PATH."""
        for cmd in ("pdflatex", "xelatex"):
            try:
                result = subprocess.run(
                    [cmd, "--version"],
                    capture_output=True,
                    timeout=3,
                    **_hidden_subprocess_kwargs(),
                )
                if result.returncode == 0:
                    full_path = shutil.which(cmd)
                    print(f"[LaTeX] Detected {cmd}: {full_path}")
                    return full_path
            except Exception:
                pass

        return None

    def is_available(self) -> bool:
        """Return whether the configured LaTeX executable is available."""
        return self.latex_cmd is not None and Path(self.latex_cmd).exists()

    def render_to_svg(self, latex_code: str) -> Optional[str]:
        """Render a LaTeX formula to SVG, returning None on failure."""
        if not self.is_available():
            print("[LaTeX] LaTeX is unavailable; skip SVG rendering")
            return None
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_dir = Path(tmpdir)
                tex_file = tmp_dir / "formula.tex"
                pdf_file = tmp_dir / "formula.pdf"
                svg_file = tmp_dir / "formula.svg"

                tex_content = self._create_tex_file(latex_code)
                tex_file.write_text(tex_content, encoding="utf-8")
                print(f"[LaTeX] Compile: {latex_code[:50]}")

                compile_result = subprocess.run(
                    [
                        self.latex_cmd,
                        "-interaction=nonstopmode",
                        "-output-directory",
                        str(tmp_dir),
                        str(tex_file),
                    ],
                    capture_output=True,
                    timeout=10,
                    text=True,
                    **_hidden_subprocess_kwargs(),
                )
                if compile_result.returncode != 0:
                    print(f"[ERROR] LaTeX compile failed:\n{compile_result.stdout}")
                    return None

                try:
                    pdftocairo_result = subprocess.run(
                        ["pdftocairo", "-svg", str(pdf_file), str(svg_file)],
                        capture_output=True,
                        timeout=10,
                        **_hidden_subprocess_kwargs(),
                    )
                    if pdftocairo_result.returncode == 0 and svg_file.exists():
                        svg_content = svg_file.read_text(encoding="utf-8")
                        print(f"[LaTeX] Rendered SVG: {len(svg_content)} bytes")
                        return self._enlarge_svg(svg_content, scale=1.6)
                except FileNotFoundError:
                    print("[WARN] pdftocairo was not found; cannot convert PDF to SVG")
                    return None
        except subprocess.TimeoutExpired:
            print("[ERROR] LaTeX compile timed out")
        except Exception as e:
            print(f"[ERROR] LaTeX render failed: {e}")
        return None

    def _enlarge_svg(self, svg_content: str, scale: float = 2.0) -> str:
        """Scale width and height attributes in generated SVG output."""

        def _scale_attr(match):
            name = match.group(1)
            value = match.group(2)
            unit = match.group(3) or ""
            try:
                scaled = float(value) * float(scale)
                return f'{name}="{scaled:g}{unit}"'
            except Exception:
                return match.group(0)

        return re.sub(
            r'\b(width|height)="([0-9]+(?:\.[0-9]+)?)(pt|px|cm|mm|in)?"',
            _scale_attr,
            svg_content,
            count=2,
        )

    def _create_tex_file(self, latex_code: str) -> str:
        """Create a tightly cropped LaTeX document for one formula."""
        return rf"""
    \documentclass{{article}}
    \usepackage{{amsmath}}
    \usepackage{{amssymb}}
    \usepackage{{amsthm}}
    \usepackage[active,tightpage]{{preview}}
    \PreviewBorder=1pt
    \pagestyle{{empty}}
    \begin{{document}}
    \begin{{preview}}
    \normalsize
    $\displaystyle {latex_code}$
    \end{{preview}}
    \end{{document}}
    """


class TypstRenderer:
    """Render LaTeX formulas to SVG or Typst documents to PDF via Typst CLI."""

    def __init__(self, typst_cmd: Optional[str] = None):
        self.typst_cmd = typst_cmd
        self._validate_typst()

    def _validate_typst(self):
        """Validate the configured Typst executable."""
        if self.typst_cmd is None:
            self.typst_cmd = self._detect_typst()

        if self.typst_cmd and not Path(self.typst_cmd).exists():
            print(f"[WARN] Typst path does not exist: {self.typst_cmd}")
            self.typst_cmd = None

    def _detect_typst(self) -> Optional[str]:
        """Detect typst from PATH."""
        try:
            result = subprocess.run(
                ["typst", "--version"],
                capture_output=True,
                timeout=5,
                **_hidden_subprocess_kwargs(),
            )
            if result.returncode == 0:
                full_path = shutil.which("typst")
                print(f"[Typst] Detected typst: {full_path}")
                return full_path
        except Exception:
            pass
        return None

    def is_available(self) -> bool:
        """Return whether Typst CLI is available."""
        return self.typst_cmd is not None and Path(self.typst_cmd).exists()

    def _convert_latex_to_typst(self, latex_code: str) -> str:
        """Convert a LaTeX formula string to Typst math syntax via pypandoc."""
        if pypandoc is None:
            return latex_code
        try:
            result = str(pypandoc.convert_text(str(latex_code), "typst", format="latex")).strip()
            print(f"[Typst] Pandoc conversion: {latex_code[:50]} -> {result[:50]}")
            return result
        except Exception as e:
            print(f"[Typst] Pandoc conversion failed: {e}, using raw LaTeX")
            return str(latex_code)

    def _create_typst_formula_doc(self, typst_math: str) -> str:
        """Create a minimal Typst document wrapping a single formula."""
        escaped = str(typst_math).replace('"', '\\"')
        return f'#set page(width: auto, height: auto, margin: 3pt)\n$ {escaped} $'

    def render_to_svg(self, latex_code: str) -> Optional[str]:
        """Render a LaTeX formula to SVG via Typst. Returns SVG string or None."""
        if not self.is_available():
            print("[Typst] Typst is unavailable; skip SVG rendering")
            return None
        try:
            # Step 1: Convert LaTeX to Typst math syntax
            typst_math = self._convert_latex_to_typst(latex_code)

            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_dir = Path(tmpdir)
                typ_file = tmp_dir / "formula.typ"
                svg_file = tmp_dir / "formula.svg"

                typ_content = self._create_typst_formula_doc(typst_math)
                typ_file.write_text(typ_content, encoding="utf-8")
                print(f"[Typst] Compile formula: {typst_math[:50]}")

                compile_result = subprocess.run(
                    [
                        self.typst_cmd,
                        "compile",
                        "--format", "svg",
                        "--root", str(tmp_dir),
                        str(typ_file),
                        str(svg_file),
                    ],
                    capture_output=True,
                    timeout=15,
                    text=True,
                    **_hidden_subprocess_kwargs(),
                )
                if compile_result.returncode != 0:
                    print(f"[ERROR] Typst compile failed:\n{compile_result.stderr}")
                    return None

                if svg_file.exists():
                    svg_content = svg_file.read_text(encoding="utf-8")
                    print(f"[Typst] Rendered SVG: {len(svg_content)} bytes")
                    return self._clean_typst_svg(svg_content)
        except subprocess.TimeoutExpired:
            print("[ERROR] Typst compile timed out")
        except Exception as e:
            print(f"[ERROR] Typst render failed: {e}")
        return None

    def _clean_typst_svg(self, svg_content: str) -> str:
        """Remove XML declaration from Typst SVG output and scale if needed."""
        # Typst outputs SVG with XML declaration; remove it for embedding.
        content = str(svg_content).strip()
        if content.startswith("<?xml"):
            idx = content.find(">")
            if idx >= 0:
                content = content[idx + 1:].strip()
        return content

    def compile_document_to_pdf(
        self,
        typst_content: str,
        output_dir: Path,
        jobname: str = "document_preview",
        timeout: int = 30,
    ) -> Optional[Path]:
        """Compile a full Typst document to PDF. Returns PDF path or None."""
        if not self.is_available():
            print("[Typst] Typst is unavailable; skip PDF compilation")
            return None
        try:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            typ_file = output_path / f"{jobname}.typ"
            pdf_file = output_path / f"{jobname}.pdf"

            typ_file.write_text(str(typst_content), encoding="utf-8")
            print(f"[Typst] Compile document: {typ_file}")

            result = subprocess.run(
                [
                    self.typst_cmd,
                    "compile",
                    "--root", str(output_path),
                    str(typ_file),
                    str(pdf_file),
                ],
                capture_output=True,
                timeout=timeout,
                text=True,
                **_hidden_subprocess_kwargs(),
            )
            if result.returncode != 0:
                print(f"[ERROR] Typst document compile failed:\n{result.stderr}")
                return None

            if pdf_file.exists():
                print(f"[Typst] PDF compiled: {pdf_file}")
                return pdf_file
        except subprocess.TimeoutExpired:
            print("[ERROR] Typst document compile timed out")
        except Exception as e:
            print(f"[ERROR] Typst document compile failed: {e}")
        return None

    def convert_latex_document_to_typst(self, latex_document: str) -> str:
        """Convert a full LaTeX document to Typst via pypandoc."""
        if pypandoc is None:
            return str(latex_document)
        try:
            result = str(pypandoc.convert_text(
                str(latex_document), "typst", format="latex"
            )).strip()
            print(f"[Typst] Document conversion: {len(latex_document)} -> {len(result)} chars")
            return result
        except Exception as e:
            print(f"[Typst] Document conversion failed: {e}")
            return str(latex_document)


class LaTeXSettings:
    """Manage persisted LaTeX rendering settings."""

    def __init__(self, config_file: Path):
        self.config_file = Path(config_file)
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        self.settings = self._load_settings()

    def _load_settings(self) -> Dict:
        """Load settings from disk."""
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[WARN] Failed to load LaTeX settings: {e}")

        return self._default_settings()

    def _default_settings(self) -> Dict:
        """Return default settings."""
        return {
            "render_mode": "auto",
            "latex_path": None,
            "typst_path": None,
            "use_xelatex": False,
            "cache_svg": True,
            "enable_offline": False,
        }

    def save(self):
        """Save settings to disk."""
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2, ensure_ascii=False)
            print(f"[LaTeX] Settings saved: {self.config_file}")
        except Exception as e:
            print(f"[ERROR] Failed to save LaTeX settings: {e}")

    def set_latex_path(self, path: str):
        """Set the LaTeX executable path."""
        self.settings["latex_path"] = path
        self.save()

    def get_latex_path(self) -> Optional[str]:
        """Return the configured LaTeX executable path."""
        return self.settings.get("latex_path")

    def set_render_mode(self, mode: str):
        """Set the formula rendering mode."""
        valid_modes = ["auto", "mathjax_local", "mathjax_cdn", "latex_pdflatex", "latex_xelatex", "typst"]

        if mode not in valid_modes:
            print(f"[WARN] Invalid render mode: {mode}")
            return

        self.settings["render_mode"] = mode

        if mode == "latex_xelatex":
            self.settings["use_xelatex"] = True
        elif mode == "latex_pdflatex":
            self.settings["use_xelatex"] = False

        self.save()

    def get_render_mode(self) -> str:
        """Return the configured render mode."""
        return self.settings.get("render_mode", "auto")

    def get_typst_path(self) -> Optional[str]:
        """Return the configured Typst executable path."""
        return self.settings.get("typst_path")

    def set_typst_path(self, path: str):
        """Set the Typst executable path."""
        self.settings["typst_path"] = path
        self.save()


_latex_renderer = None
_typst_renderer = None
_latex_settings = None


def init_latex_settings(config_dir: Path) -> LaTeXSettings:
    """Initialize LaTeX settings."""
    global _latex_settings
    config_file = config_dir / "latex_settings.json"
    _latex_settings = LaTeXSettings(config_file)
    return _latex_settings


def get_latex_renderer() -> LaTeXRenderer:
    """Return the shared LaTeX renderer instance."""
    global _latex_renderer, _latex_settings

    if _latex_renderer is None:
        latex_path = _latex_settings.get_latex_path() if _latex_settings else None
        _latex_renderer = LaTeXRenderer(latex_path)

    return _latex_renderer


def get_typst_renderer() -> TypstRenderer:
    """Return the shared Typst renderer instance."""
    global _typst_renderer, _latex_settings

    if _typst_renderer is None:
        typst_path = _latex_settings.get_typst_path() if _latex_settings else None
        _typst_renderer = TypstRenderer(typst_path)

    return _typst_renderer
