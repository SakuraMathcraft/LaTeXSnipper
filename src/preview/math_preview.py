"""MathJax preview HTML, theme tokens, and formula export helpers."""

from __future__ import annotations

import re
from pathlib import Path

from PyQt6.QtWidgets import QApplication

APP_DIR: Path | None = None


def configure_math_preview_runtime(app_dir: Path | str | None) -> None:
    global APP_DIR
    APP_DIR = Path(app_dir) if app_dir else None

MATHJAX_CDN_URL = "https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-mml-chtml.js"
# 备用CDN（如主CDN不可用）
MATHJAX_CDN_URL_BACKUP = "https://cdnjs.cloudflare.com/ajax/libs/mathjax/3.2.2/es5/tex-mml-chtml.js"


def is_dark_ui() -> bool:
    try:
        import qfluentwidgets as qfw
        fn = getattr(qfw, "isDarkTheme", None)
        if callable(fn):
            return bool(fn())
    except Exception:
        pass
    app = QApplication.instance()
    if app is None:
        return False
    c = app.palette().window().color()
    return ((c.red() + c.green() + c.blue()) / 3.0) < 128


def preview_theme_tokens() -> dict:
    if is_dark_ui():
        return {
            "body_bg": "#14171d",
            "body_text": "#e8ebf0",
            "latex_formula_text": "#ffffff",
            "panel_bg": "#1d222b",
            "label_text": "#8ec5ff",
            "label_bg": "#1e334a",
            "error_text": "#ff9a9a",
            "error_bg": "#4a1f27",
            "muted_text": "#95a0af",
            "pre_bg": "#342b20",
            "border_formula": "#63a5ff",
            "border_text": "#72d68e",
            "border_table": "#ffb35c",
            "border_mixed": "#d8a4ff",
            "badge_formula_bg": "#23374d",
            "badge_formula_text": "#9fd1ff",
            "badge_text_bg": "#213328",
            "badge_text_text": "#88d5a3",
            "badge_table_bg": "#3a2a18",
            "badge_table_text": "#ffbf7a",
            "badge_mixed_bg": "#35253f",
            "badge_mixed_text": "#e4bcff",
            "table_border": "#3e4958",
            "th_bg": "#27303b",
        }
    return {
        "body_bg": "#fafafa",
        "body_text": "#1f2328",
        "latex_formula_text": "#1f2328",
        "panel_bg": "#f8f9fa",
        "label_text": "#1976d2",
        "label_bg": "#e3f2fd",
        "error_text": "#d32f2f",
        "error_bg": "#ffebee",
        "muted_text": "#888888",
        "pre_bg": "#fff3e0",
        "border_formula": "#1976d2",
        "border_text": "#43a047",
        "border_table": "#f57c00",
        "border_mixed": "#7b1fa2",
        "badge_formula_bg": "#e3f2fd",
        "badge_formula_text": "#1976d2",
        "badge_text_bg": "#e8f5e9",
        "badge_text_text": "#43a047",
        "badge_table_bg": "#fff3e0",
        "badge_table_text": "#f57c00",
        "badge_mixed_bg": "#f3e5f5",
        "badge_mixed_text": "#7b1fa2",
        "table_border": "#dddddd",
        "th_bg": "#f2f2f2",
    }


def formula_label_theme_tokens() -> dict:
    if is_dark_ui():
        return {
            "text": "#d7dee9",
            "tooltip_bg": "#27303b",
            "tooltip_text": "#eef3f8",
            "tooltip_border": "#4d5a6b",
        }
    return {
        "text": "#333333",
        "tooltip_bg": "#ffffff",
        "tooltip_text": "#1f2328",
        "tooltip_border": "#cfd6df",
    }


def dialog_theme_tokens() -> dict:
    if is_dark_ui():
        return {
            "window_bg": "#1b1f27",
            "panel_bg": "#232934",
            "text": "#e7ebf0",
            "muted": "#a9b3bf",
            "border": "#465162",
            "accent": "#8ec5ff",
        }
    return {
        "window_bg": "#ffffff",
        "panel_bg": "#f7f9fc",
        "text": "#222222",
        "muted": "#666666",
        "border": "#d0d7de",
        "accent": "#1976d2",
    }


# 支持 SVG 渲染的简化模板（不需要 MathJax 脚本）
MATHJAX_HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<!-- 【关键】允许本地文件加载和不安全内容（桌面应用必需） -->
<meta http-equiv="Content-Security-Policy" content="default-src * 'unsafe-inline' 'unsafe-eval' data: blob: file:; script-src * 'unsafe-inline' 'unsafe-eval'; style-src * 'unsafe-inline';">
<style>
body {
  font-family: 'Segoe UI', 'Microsoft YaHei UI', sans-serif;
  padding: 12px;
  margin: 0;
    background: __BODY_BG__;
    color: __BODY_TEXT__;
  font-size: 18px;
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}
.math-container {
  overflow-x: auto;
  padding: 0;
  text-align: center;
  margin-bottom: 12px;
  position: relative;
  min-height: 0;
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}
.math-container:last-child {
  margin-bottom: 0;
}
.formula-label {
  position: absolute;
  top: 4px;
  left: 8px;
  font-size: 12px;
    color: __LABEL_TEXT__;
    background: __LABEL_BG__;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 500;
}
.formula-content {
  display: inline-block;
  max-width: 100%;
  overflow: auto;
  padding: 0;
  margin: 0;
  font-size: 20px;
}
.error-text {
    color: __ERROR_TEXT__;
  font-size: 12px;
  padding: 8px;
    background: __ERROR_BG__;
  border-radius: 4px;
}
</style>
<!-- MathJax 配置 -->
<script>
  window.MathJax = {
    tex: {
      inlineMath: [['$', '$'], ['\\(', '\\)']],
      displayMath: [['$$', '$$'], ['\\[', '\\]']],
      processEscapes: true
    },
    svg: {
      fontCache: 'global',
            scale: 1.15
    },
    options: {
      enableMenu: false,
      skipHtmlTags: [],
      ignoreHtmlClass: [],
      processHtmlClass: []
    }
  };
</script>
</head>
<body>
__FORMULAS__
<!-- MathJax 加载：优先本地，失败则使用 CDN -->
<script>
(function() {
  var shouldLogLocalFallback = __LOG_MATHJAX_LOCAL_FALLBACK__;
  // 尝试本地加载
  var localScript = 'tex-mml-chtml.js';
  var cdnUrls = [
    'https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-mml-chtml.js',
    'https://cdnjs.cloudflare.com/ajax/libs/mathjax/3.2.2/es5/tex-mml-chtml.js'
  ];
  
  var script = document.createElement('script');
  script.type = 'text/javascript';
  script.async = true;
  
  // 本地加载失败时使用 CDN
  script.onerror = function() {
    if (shouldLogLocalFallback) {
      console.warn('[MathJax] 本地加载失败，尝试使用 CDN...');
    }
    var cdnScript = document.createElement('script');
    cdnScript.src = cdnUrls[0];
    cdnScript.type = 'text/javascript';
    cdnScript.async = true;
    document.body.appendChild(cdnScript);
  };
  
  script.src = localScript;
  document.body.appendChild(script);
})();
</script>
</body>
</html>
"""

_MATHJAX_LOGGED_KEYS = set()


def get_mathjax_base_url():
    """获取 MathJax 的 base URL (用于 setHtml)
    
    这个函数必须返回一个指向 es5 目录的 file:// URL，
    这样 tex-mml-chtml.js 才能被正确加载。
    
    支持开发模式和 PyInstaller 打包后的两种运行环境。
    """
    from PyQt6.QtCore import QUrl
    from pathlib import Path
    import sys
    
    try:
        # 首先检查当前选择的渲染模式
        try:
            from backend.latex_renderer import _latex_settings
            if _latex_settings:
                mode = _latex_settings.get_render_mode()
                # 如果选择了 CDN MathJax，返回 CDN URL
                if mode == "mathjax_cdn":
                    if "cdn" not in _MATHJAX_LOGGED_KEYS:
                        print("[MathJax] 使用 CDN MathJax")
                        _MATHJAX_LOGGED_KEYS.add("cdn")
                    cdn_url = "https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/"
                    return QUrl(cdn_url)
                # LaTeX 模式下主窗口/结果窗口仍可能包含 MathJax 内容（如混合文本、回退渲染），
                # 这里继续返回本地 base_url，避免空 base 触发 CDN 回退。
                elif mode and mode.startswith("latex_"):
                    mode_key = f"latex:{mode}"
                    if mode_key not in _MATHJAX_LOGGED_KEYS:
                        print(f"[MathJax] LaTeX 模式下仍使用本地 MathJax base: {mode}")
                        _MATHJAX_LOGGED_KEYS.add(mode_key)
                    # continue: resolve local MathJax base URL below
        except Exception as e:
            print(f"[WARN] 获取渲染模式失败: {e}")
        
        # 否则使用本地 MathJax
        # 第1步：确定 APP_DIR
        actual_app_dir = None
        
        # 优先使用全局 APP_DIR（已初始化的情况）
        if APP_DIR and str(APP_DIR).strip():
            actual_app_dir = Path(APP_DIR)
        
        mathjax_source_desc = "本地资源"

        # 如果 APP_DIR 为空或不可用，尝试其他方法
        if not actual_app_dir or not str(actual_app_dir).strip():
            # 打包模式检查：sys.frozen 表示 PyInstaller 打包
            if getattr(sys, 'frozen', False):
                # 打包后：exe 所在目录的 _internal 或同级 src
                exe_dir = Path(sys.executable).parent
                # 尝试 _internal/assets (PyInstaller --onedir)
                if (exe_dir / "_internal" / "assets").exists():
                    actual_app_dir = exe_dir / "_internal"
                    mathjax_source_desc = "_internal"
                # 尝试 assets (PyInstaller --onefile 解包目录)
                elif (exe_dir / "assets").exists():
                    actual_app_dir = exe_dir
                    mathjax_source_desc = "exe 同级"
                else:
                    # 最后尝试：还原到 exe 目录往上查找
                    parent = exe_dir.parent
                    if (parent / "src" / "assets").exists():
                        actual_app_dir = parent / "src"
                        mathjax_source_desc = "父目录 src"
            else:
                # 开发模式：使用当前脚本所在目录
                actual_app_dir = Path(__file__).parent
                mathjax_source_desc = "__file__"
        
        if not actual_app_dir:
            actual_app_dir = Path(APP_DIR) if APP_DIR else Path.cwd()
        
        # 第2步：检查 MathJax es5 目录
        es5_dir = actual_app_dir / "assets" / "MathJax-3.2.2" / "es5"
        tex_chtml = es5_dir / "tex-mml-chtml.js"
        
        if not tex_chtml.exists():
            print(f"[WARN] MathJax 文件缺失: {tex_chtml}")
        
        # 第3步：生成 file:// URL
        # 在 Windows 上需要正确处理路径分隔符
        # QUrl.fromLocalFile 需要规范化路径
        url_path = str(es5_dir).replace("\\", "/")  # 转换为前向斜杠
        if not url_path.endswith("/"):
            url_path += "/"
        
        # 使用 QUrl.fromLocalFile() 
        # 注意：QUrl.fromLocalFile() 自动处理 file:// 前缀
        url = QUrl.fromLocalFile(str(es5_dir) + "/")
        url_str = url.toString()
        
        if not url_str.startswith("file:///"):
            print(f"[ERROR] URL 格式异常，应以 file:/// 开头: {url_str}")
        else:
            local_key = f"local:{mathjax_source_desc}:{url_str}"
            if local_key not in _MATHJAX_LOGGED_KEYS:
                label = "使用本地资源" if mathjax_source_desc == "本地资源" else f"使用本地资源({mathjax_source_desc})"
                print(f"[MathJax] {label}: {url_str}")
                _MATHJAX_LOGGED_KEYS.add(local_key)
        
        return url
        
    except Exception as e:
        print(f"[ERROR] get_mathjax_base_url 异常: {e}")
        import traceback
        traceback.print_exc()
        # 返回临时路径作为后备方案
        return QUrl.fromLocalFile("/")

def latex_to_svg(latex: str) -> str:
    """将 LaTeX 公式转换为 SVG 字符串（使用 matplotlib）
    
    Args:
        latex: LaTeX 公式字符串，例如 "\\frac{1}{2}"
        
    Returns:
        SVG 字符串，如果转换失败返回原始 LaTeX 文本
    """
    try:
        import matplotlib
        matplotlib.use('Agg')  # 使用无头后端
        import matplotlib.pyplot as plt
        from io import BytesIO
        
        # 创建图形并渲染公式
        fig, ax = plt.subplots(figsize=(8, 1), dpi=150)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')
        
        # 使用 mathtext 渲染公式
        ax.text(0.5, 0.5, f'${latex}$', ha='center', va='center', 
            fontsize=16, transform=ax.transAxes)
        
        # 保存为 SVG
        svg_buffer = BytesIO()
        plt.savefig(svg_buffer, format='svg', bbox_inches='tight', pad_inches=0.1, 
                   facecolor='white', edgecolor='none')
        plt.close(fig)
        
        # 获取 SVG 内容
        svg_buffer.seek(0)
        svg_str = svg_buffer.getvalue().decode('utf-8')
        
        # 清理 SVG（移除 XML 声明和样式）
        svg_str = svg_str.replace('<?xml version', '<!-- SVG from matplotlib -->\n<?xml version')
        
        return svg_str
        
    except Exception as e:
        print(f"[ERROR] LaTeX to SVG conversion failed: {e}")
        raise

_MATHML_SUM = "\u2211"
_MATHML_INF = "\u221E"

def _strip_math_delimiters(latex: str) -> str:
    t = (latex or "").strip()
    if len(t) >= 4 and t.startswith("$$") and t.endswith("$$"):
        return t[2:-2].strip()
    if len(t) >= 2 and t.startswith("$") and t.endswith("$"):
        return t[1:-1].strip()
    return t

def normalize_latex_for_export(latex: str) -> str:
    """规范化导出用 LaTeX：简化单字符上下标、补充必要空格。"""
    t = _strip_math_delimiters(latex)
    if not t:
        return ""
    t = re.sub(r"\^\{([A-Za-z0-9])\}", r"^\1", t)
    t = re.sub(r"_\{([A-Za-z0-9])\}", r"_\1", t)
    t = t.replace(":=", " := ")
    t = re.sub(r"(?<=\S)(\\(?:sum))", r" \1", t)
    t = re.sub(r"(?<=\S)(\\(?:frac|dfrac|tfrac))", r" \1", t)
    t = re.sub(r"[ \t]+", " ", t).strip()
    return t

def latex_inline(latex: str) -> str:
    return f"${latex}$"

def latex_display(latex: str) -> str:
    return f"\\[\n{latex}\n\\]"

def latex_equation(latex: str) -> str:
    return f"\\begin{{equation}}\n{latex}\n\\end{{equation}}"

def _ensure_mathml_block(mathml: str) -> str:
    if not mathml:
        return mathml
    m = re.search(r"<math\b([^>]*)>", mathml)
    if not m:
        return mathml
    attrs = m.group(1) or ""
    if re.search(r"\bdisplay\s*=", attrs):
        return mathml
    sep = " " if attrs and not attrs.endswith(" ") else ""
    new_tag = f"<math{attrs}{sep}display=\"block\">"
    return mathml[:m.start()] + new_tag + mathml[m.end():]

def mathml_standardize(mathml: str) -> str:
    """标准 MathML：保证 display=block，统一无穷符号样式。"""
    mathml = _ensure_mathml_block(mathml)
    # 合并 := 到单个 <mo>
    mathml = re.sub(r"<mo>\s*:</mo>\s*<mo>\s*=\s*</mo>", "<mo>:=</mo>", mathml)
    mathml = re.sub(
        r"<mi>\s*(?:&#x221E;|&#X221E;|%s)\s*</mi>" % _MATHML_INF,
        '<mi mathvariant="normal">&#x221E;</mi>',
        mathml,
    )
    mathml = mathml.replace(_MATHML_SUM, "&#x2211;").replace(_MATHML_INF, "&#x221E;")
    return mathml

def _mathml_htmlize(mathml: str) -> str:
    """HTML 用 MathML：display=block，sum 增加 data-mjx-texclass，符号转 Unicode。"""
    mathml = _ensure_mathml_block(mathml)
    # 合并 := 到单个 <mo>
    mathml = re.sub(r"<mo>\s*:</mo>\s*<mo>\s*=\s*</mo>", "<mo>:=</mo>", mathml)
    mathml = re.sub(
        r"<mi>\s*(?:&#x221E;|&#X221E;|%s)\s*</mi>" % _MATHML_INF,
        f'<mi mathvariant="normal">{_MATHML_INF}</mi>',
        mathml,
    )

    def _sum_repl(match):
        attrs = match.group(1) or ""
        if "data-mjx-texclass" in attrs:
            return f"<mo{attrs}>{_MATHML_SUM}</mo>"
        sep = "" if not attrs or attrs.endswith(" ") else " "
        return f"<mo{attrs}{sep}data-mjx-texclass=\"OP\">{_MATHML_SUM}</mo>"

    mathml = re.sub(
        r"<mo([^>]*)>\s*(?:&#x2211;|&#X2211;|%s)\s*</mo>" % _MATHML_SUM,
        _sum_repl,
        mathml,
        count=1,
    )
    mathml = mathml.replace("&#x2211;", _MATHML_SUM).replace("&#X2211;", _MATHML_SUM)
    mathml = mathml.replace("&#x221E;", _MATHML_INF).replace("&#X221E;", _MATHML_INF)
    return mathml

def mathml_to_html_fragment(mathml: str) -> str:
    """将 MathML 包装为可直接嵌入网页的 HTML 片段。"""
    html_mathml = _mathml_htmlize(mathml)
    return f'<span class="latexsnipper-math" data-format="mathml">{html_mathml}</span>'

def mathml_with_prefix(mathml: str, prefix: str) -> str:
    """将 MathML 标签统一加命名空间前缀，如 mml:, m:, attr:。"""
    if not mathml:
        return mathml
    mathml = _ensure_mathml_block(mathml)

    def _root_repl(match):
        attrs = match.group(1) or ""
        attrs = re.sub(r'\s+xmlns="[^"]*"', "", attrs)
        if f"xmlns:{prefix}=" not in attrs:
            sep = " " if attrs and not attrs.endswith(" ") else ""
            attrs = f'{attrs}{sep}xmlns:{prefix}="http://www.w3.org/1998/Math/MathML"'
        return f"<{prefix}:math{attrs}>"

    mathml = re.sub(r"<math\b([^>]*)>", _root_repl, mathml, count=1)
    mathml = re.sub(r"</math>", f"</{prefix}:math>", mathml)

    def _tag_repl(match):
        slash, name, rest = match.group(1), match.group(2), match.group(3)
        if ":" in name:
            return match.group(0)
        return f"<{slash}{prefix}:{name}{rest}>"

    return re.sub(r"<(/?)([A-Za-z][A-Za-z0-9:.-]*)(\b[^>]*)>", _tag_repl, mathml)

def build_math_html(latex_or_list, labels=None) -> str:
    """构建 MathJax 渲染 HTML，支持单个公式或公式列表
    
    Args:
        latex_or_list: 单个公式字符串或公式列表
        labels: 可选的标签列表，与公式一一对应
    
    注意：返回的 HTML 使用相对路径加载脚本，必须通过 setHtml(html, base_url) 使用！
    """
    try:
        if isinstance(latex_or_list, str):
            formulas = [latex_or_list] if latex_or_list.strip() else []
        else:
            formulas = [f for f in latex_or_list if f and f.strip()]
        
        if labels is None:
            labels = [None] * len(formulas)
        
        tokens = preview_theme_tokens()

        # 生成每个公式的 MathJax HTML
        formula_html = ""
        for i, latex in enumerate(formulas):
            label = labels[i] if i < len(labels) and labels[i] else ""
            label_html = f'<div class="formula-label">{label}</div>' if label else ""
            
            # 使用 MathJax 渲染（不要 HTML 转义，保留 LaTeX）
            formula_html += f'<div class="math-container">{label_html}<div class="formula-content">$${latex}$$</div></div>\n'
        
        if not formula_html:
            formula_html = f'<div class="math-container" style="color:{tokens["muted_text"]};">无公式</div>'

        log_local_fallback = True
        try:
            from backend.latex_renderer import _latex_settings
            mode = _latex_settings.get_render_mode() if _latex_settings else "auto"
            log_local_fallback = mode in ("auto", "mathjax_local")
        except Exception:
            pass
        
        # 使用 MathJax HTML 模板（使用相对路径）
        html = MATHJAX_HTML_TEMPLATE.replace("__FORMULAS__", formula_html)
        html = html.replace("__LOG_MATHJAX_LOCAL_FALLBACK__", "true" if log_local_fallback else "false")
        html = html.replace("__BODY_BG__", tokens["body_bg"])
        html = html.replace("__BODY_TEXT__", tokens["body_text"])
        html = html.replace("__LABEL_TEXT__", tokens["label_text"])
        html = html.replace("__LABEL_BG__", tokens["label_bg"])
        html = html.replace("__ERROR_TEXT__", tokens["error_text"])
        html = html.replace("__ERROR_BG__", tokens["error_bg"])
        
        return html
    except Exception as e:
        print(f"[ERROR] build_math_html 出错: {e}")
        import traceback
        traceback.print_exc()
        # 返回错误提示 HTML
        tokens = preview_theme_tokens()
        return f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"/></head>
    <body style="color: {tokens['error_text']}; background: {tokens['body_bg']}; padding: 20px; font-family: sans-serif;">
<h3>公式渲染出错</h3>
<p><strong>错误信息:</strong> {str(e)}</p>
<p>请检查 MathJax 资源是否正确打包</p>
</body></html>'''

