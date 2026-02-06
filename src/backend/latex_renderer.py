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
from pathlib import Path
from typing import Optional, Dict
import json


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
                    timeout=3
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
                    text=True
                )
                if compile_result.returncode != 0:
                    print(f"[ERROR] LaTeX 编译失败:\n{compile_result.stdout}")
                    return None
                # 3. 转换 PDF 到 SVG（使用 pdftocairo）
                try:
                    pdftocairo_result = subprocess.run(
                        ["pdftocairo", "-svg", str(pdf_file), str(svg_file)],
                        capture_output=True,
                        timeout=10
                    )
                    if pdftocairo_result.returncode == 0 and svg_file.exists():
                        svg_content = svg_file.read_text(encoding='utf-8')
                        print(f"[LaTeX] 渲染成功: {len(svg_content)} bytes")
                        # 方案二：自动放大 SVG
                        svg_content = self._enlarge_svg(svg_content, scale=20.0)
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
        # 匹配 <svg ... width="..." height="..." viewBox="... ... w h" ...>
        def repl(match):
            width = match.group("width")
            height = match.group("height")
            viewbox = match.group("viewbox")
            # 放大 width/height
            try:
                w = float(width)
                h = float(height)
                w2 = w * scale
                h2 = h * scale
                width_str = f'{w2:g}'
                height_str = f'{h2:g}'
            except Exception:
                width_str = width
                height_str = height
            # viewBox="x y w h"，只放大 w h
            if viewbox:
                vb = viewbox.split()
                if len(vb) == 4:
                    try:
                        vb[2] = str(float(vb[2]) * scale)
                        vb[3] = str(float(vb[3]) * scale)
                    except Exception:
                        pass
                    viewbox_str = 'viewBox="' + ' '.join(vb) + '"'
                else:
                    viewbox_str = f'viewBox="{viewbox}"'
            else:
                viewbox_str = ''
            return f'<svg width="{width_str}" height="{height_str}" {viewbox_str}'
        # 替换 <svg ...>
        svg_content = re.sub(
            r'<svg\s+[^>]*width="(?P<width>[0-9.]+)"\s+height="(?P<height>[0-9.]+)"(?:\s+viewBox="(?P<viewbox>[^"]+)")?',
            repl,
            svg_content,
            count=1
        )
        return svg_content
    
    def _create_tex_file(self, latex_code: str) -> str:
        """创建 LaTeX 源文件内容（加大字号）"""
        return rf"""
    \documentclass{{article}}
    \usepackage{{amsmath}}
    \usepackage{{amssymb}}
    \usepackage{{amsthm}}
    \usepackage{{geometry}}
    \geometry{{margin=0.5in}}
    \pagestyle{{empty}}
    \begin{{document}}
    \Huge
    ${latex_code}$
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
