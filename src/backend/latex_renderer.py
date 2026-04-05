"""
LaTeX 公式渲染器 - 支持 pdflatex/xelatex 或 MathJax 备选

用户可以在设置中指定 LaTeX 环境路径：
- Windows: C:\Program Files\MiKTeX\miktex\bin\x64\pdflatex.exe
- Linux: /usr/bin/pdflatex
- macOS: /Library/TeX/texbin/pdflatex
"""

import subprocess
import tempfile
import shutil
import os
import re
from pathlib import Path
from typing import Optional, Dict, Tuple
import json


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
    return str(mode or "").strip() in {"latex_pdflatex", "latex_xelatex"}


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


def compile_tex_document(
    tex_content: str,
    output_dir: Path,
    jobname: str = "document_preview",
    timeout: int = 25,
) -> Tuple[Optional[Path], str]:
    mode = get_document_render_mode()
    if not is_supported_document_render_mode(mode):
        return None, "请先在设置中选择 LaTeX + pdflatex 或 LaTeX + xelatex。"

    latex_path = _latex_settings.get_latex_path() if _latex_settings else None
    latex_cmd = _resolve_latex_command_for_mode(mode, latex_path)
    if not latex_cmd:
        engine_name = "xelatex" if mode == "latex_xelatex" else "pdflatex"
        return None, f"未找到可用的 {engine_name}，请先在设置中完成 LaTeX 路径配置。"

    text = str(tex_content or "").strip()
    if not text:
        return None, "当前没有可编译的 TeX 文档内容。"

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    tex_file = output_path / f"{jobname}.tex"
    pdf_file = output_path / f"{jobname}.pdf"
    tex_file.write_text(text, encoding="utf-8")

    try:
        result = subprocess.run(
            [
                latex_cmd,
                "-interaction=nonstopmode",
                "-halt-on-error",
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
    except subprocess.TimeoutExpired:
        return None, "TeX 文档编译超时，请检查内容或 LaTeX 环境。"
    except Exception as exc:
        return None, f"TeX 文档编译失败: {exc}"

    if result.returncode != 0 or not pdf_file.exists():
        log_text = "\n".join(filter(None, [result.stdout, result.stderr]))
        cleaned = _extract_latex_error_message(log_text, tex_file)
        if cleaned:
            cleaned = re.sub(r"\s+", " ", cleaned).strip()[:320]
        return None, cleaned or "TeX 文档编译失败，请检查源码和 LaTeX 环境。"

    return pdf_file, ""


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
    """LaTeX 公式渲染器"""
    
    def __init__(self, latex_cmd: Optional[str] = None):
        """
        初始化渲染器
        
        Args:
            latex_cmd: pdflatex 或 xelatex 的完整路径
                      如果为 None，会尝试自动检测
        """
        self.latex_cmd = latex_cmd
        self._validate_latex()
    
    def _validate_latex(self):
        """验证 LaTeX 命令是否可用"""
        if self.latex_cmd is None:
            # 尝试自动检测
            self.latex_cmd = self._detect_latex()
        
        if self.latex_cmd and not Path(self.latex_cmd).exists():
            print(f"[WARN] LaTeX 路径不存在: {self.latex_cmd}")
            self.latex_cmd = None
    
    def _detect_latex(self) -> Optional[str]:
        """自动检测系统中的 pdflatex"""
        commands = ["pdflatex", "xelatex"]
        
        for cmd in commands:
            try:
                # 尝试运行命令
                result = subprocess.run(
                    [cmd, "--version"],
                    capture_output=True,
                    timeout=3,
                    **_hidden_subprocess_kwargs(),
                )
                if result.returncode == 0:
                    # 在 Windows 上，需要获取完整路径
                    full_path = shutil.which(cmd)
                    print(f"[LaTeX] 检测到 {cmd}: {full_path}")
                    return full_path
            except Exception:
                pass
        
        return None
    
    def is_available(self) -> bool:
        """检查 LaTeX 是否可用"""
        return self.latex_cmd is not None and Path(self.latex_cmd).exists()
    
    def render_to_svg(self, latex_code: str) -> Optional[str]:
        """
        将 LaTeX 公式渲染为 SVG
        
        Args:
            latex_code: LaTeX 公式代码（如 \\frac{1}{2}）
        
        Returns:
            SVG 字符串，或 None 表示失败
        """
        import re
        if not self.is_available():
            print("[LaTeX] LaTeX 不可用，跳过渲染")
            return None
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_dir = Path(tmpdir)
                tex_file = tmp_dir / "formula.tex"
                pdf_file = tmp_dir / "formula.pdf"
                svg_file = tmp_dir / "formula.svg"
                # 1. 创建 LaTeX 源文件
                tex_content = self._create_tex_file(latex_code)
                tex_file.write_text(tex_content, encoding='utf-8')
                print(f"[LaTeX] 编译: {latex_code[:50]}")
                # 2. 编译为 PDF
                compile_result = subprocess.run(
                    [
                        self.latex_cmd,
                        "-interaction=nonstopmode",
                        "-output-directory", str(tmp_dir),
                        str(tex_file)
                    ],
                    capture_output=True,
                    timeout=10,
                    text=True,
                    **_hidden_subprocess_kwargs(),
                )
                if compile_result.returncode != 0:
                    print(f"[ERROR] LaTeX 编译失败:\n{compile_result.stdout}")
                    return None
                # 3. 转换 PDF 到 SVG（使用 pdftocairo）
                try:
                    pdftocairo_result = subprocess.run(
                        ["pdftocairo", "-svg", str(pdf_file), str(svg_file)],
                        capture_output=True,
                        timeout=10,
                        **_hidden_subprocess_kwargs(),
                    )
                    if pdftocairo_result.returncode == 0 and svg_file.exists():
                        svg_content = svg_file.read_text(encoding='utf-8')
                        print(f"[LaTeX] 渲染成功: {len(svg_content)} bytes")
                        # 适度放大 SVG，提升主窗口 LaTeX 引擎预览可读性
                        svg_content = self._enlarge_svg(svg_content, scale=2.2)
                        return svg_content
                except FileNotFoundError:
                    print("[WARN] pdftocairo 未找到，无法转换 PDF 到 SVG")
                    return None
        except subprocess.TimeoutExpired:
            print("[ERROR] LaTeX 编译超时")
        except Exception as e:
            print(f"[ERROR] LaTeX 渲染异常: {e}")
        return None

    def _enlarge_svg(self, svg_content: str, scale: float = 2.0) -> str:
        """
        自动放大 SVG 的 width/height/viewBox
        Args:
            svg_content: SVG 字符串
            scale: 放大倍数
        Returns:
            修改后的 SVG 字符串
        """
        import re

        def _scale_attr(match):
            name = match.group(1)
            value = match.group(2)
            unit = match.group(3) or ""
            try:
                scaled = float(value) * float(scale)
                return f'{name}="{scaled:g}{unit}"'
            except Exception:
                return match.group(0)

        # 仅放大 width/height；不要改 viewBox，避免抵消放大效果。
        # 兼容无单位和带单位（pt/px/cm/mm/in）的场景。
        svg_content = re.sub(
            r'\b(width|height)="([0-9]+(?:\.[0-9]+)?)(pt|px|cm|mm|in)?"',
            _scale_attr,
            svg_content,
            count=2,
        )
        return svg_content
    
    def _create_tex_file(self, latex_code: str) -> str:
        """创建 LaTeX 源文件内容（使用 preview 紧裁剪公式边界）"""
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

class LaTeXSettings:
    """LaTeX 渲染设置管理"""
    
    def __init__(self, config_file: Path):
        """
        初始化设置
        
        Args:
            config_file: 配置文件路径
        """
        self.config_file = Path(config_file)
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        self.settings = self._load_settings()
    
    def _load_settings(self) -> Dict:
        """加载设置"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"[WARN] 加载 LaTeX 设置失败: {e}")
        
        return self._default_settings()
    
    def _default_settings(self) -> Dict:
        """默认设置"""
        return {
            "render_mode": "auto",  # auto/mathjax/latex
            "latex_path": None,  # pdflatex 路径
            "use_xelatex": False,  # 是否使用 xelatex
            "cache_svg": True,  # 是否缓存 SVG
            "enable_offline": False  # 是否启用离线模式（仅 MathJax 本地）
        }
    
    def save(self):
        """保存设置"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=2, ensure_ascii=False)
            print(f"[LaTeX] 设置已保存: {self.config_file}")
        except Exception as e:
            print(f"[ERROR] 保存 LaTeX 设置失败: {e}")
    
    def set_latex_path(self, path: str):
        """设置 LaTeX 路径"""
        self.settings["latex_path"] = path
        self.save()
    
    def get_latex_path(self) -> Optional[str]:
        """获取 LaTeX 路径"""
        return self.settings.get("latex_path")
    
    def set_render_mode(self, mode: str):
        """
        设置渲染模式
        
        Args:
            mode: 'auto' (自动检测), 'mathjax_local' (本地MathJax), 
                  'mathjax_cdn' (CDN MathJax), 'latex_pdflatex' (LaTeX+pdflatex),
                  'latex_xelatex' (LaTeX+xelatex)
        """
        valid_modes = ["auto", "mathjax_local", "mathjax_cdn", "latex_pdflatex", "latex_xelatex"]
        
        if mode not in valid_modes:
            print(f"[WARN] 无效的渲染模式: {mode}")
            return
        
        self.settings["render_mode"] = mode
        
        # 如果是 LaTeX 模式，记录是否使用 xelatex
        if mode == "latex_xelatex":
            self.settings["use_xelatex"] = True
        elif mode == "latex_pdflatex":
            self.settings["use_xelatex"] = False
        
        self.save()
    
    def get_render_mode(self) -> str:
        """获取渲染模式"""
        return self.settings.get("render_mode", "auto")


# 全局实例
_latex_renderer = None
_latex_settings = None


def init_latex_settings(config_dir: Path) -> LaTeXSettings:
    """初始化 LaTeX 设置"""
    global _latex_settings
    config_file = config_dir / "latex_settings.json"
    _latex_settings = LaTeXSettings(config_file)
    return _latex_settings


def get_latex_renderer() -> LaTeXRenderer:
    """获取 LaTeX 渲染器单例"""
    global _latex_renderer, _latex_settings
    
    if _latex_renderer is None:
        # 获取用户指定的路径
        latex_path = _latex_settings.get_latex_path() if _latex_settings else None
        _latex_renderer = LaTeXRenderer(latex_path)
    
    return _latex_renderer


def render_formula(latex_code: str, prefer_latex: bool = False) -> Optional[str]:
    """
    渲染公式
    
    Args:
        latex_code: LaTeX 代码
        prefer_latex: 是否优先使用 LaTeX 渲染
    
    Returns:
        SVG 字符串或 None
    """
    renderer = get_latex_renderer()
    
    if prefer_latex and renderer.is_available():
        return renderer.render_to_svg(latex_code)
    
    return None
