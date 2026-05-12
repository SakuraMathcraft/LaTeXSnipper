"""MathJax preview HTML and theme tokens."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import QApplication

APP_DIR: Path | None = None


def configure_math_preview_runtime(app_dir: Path | str | None) -> None:
    global APP_DIR
    APP_DIR = Path(app_dir) if app_dir else None

MATHJAX_CDN_URL = "https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-mml-chtml.js"
# Backup CDN used when the primary CDN is unavailable.
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


# Simplified template for SVG rendering; MathJax scripts are not needed.
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
    """Return the MathJax base URL used by setHtml."""
    from PyQt6.QtCore import QUrl
    from pathlib import Path
    import sys
    
    try:
        # Check the currently selected render mode first.
        try:
            from backend.latex_renderer import _latex_settings
            if _latex_settings:
                mode = _latex_settings.get_render_mode()
                # Return the CDN URL when CDN MathJax is selected.
                if mode == "mathjax_cdn":
                    if "cdn" not in _MATHJAX_LOGGED_KEYS:
                        print("[MathJax] 使用 CDN MathJax")
                        _MATHJAX_LOGGED_KEYS.add("cdn")
                    cdn_url = "https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/"
                    return QUrl(cdn_url)
                # In LaTeX mode the main/result windows may still contain MathJax content such as mixed text or fallback rendering,
                # so keep returning the local base_url to avoid an empty base triggering CDN fallback.
                elif mode and mode.startswith("latex_"):
                    mode_key = f"latex:{mode}"
                    if mode_key not in _MATHJAX_LOGGED_KEYS:
                        print(f"[MathJax] LaTeX 模式下仍使用本地 MathJax base: {mode}")
                        _MATHJAX_LOGGED_KEYS.add(mode_key)
                    # continue: resolve local MathJax base URL below
        except Exception as e:
            print(f"[WARN] 获取渲染模式失败: {e}")
        
        # Otherwise use local MathJax.
        # Step 1: resolve APP_DIR.
        actual_app_dir = None
        
        # Prefer the global APP_DIR when it has already been initialized.
        if APP_DIR and str(APP_DIR).strip():
            actual_app_dir = Path(APP_DIR)
        
        mathjax_source_desc = "本地资源"

        # Try alternate locations when APP_DIR is empty or unavailable.
        if not actual_app_dir or not str(actual_app_dir).strip():
            # Packaged-mode check: sys.frozen indicates a PyInstaller build.
            if getattr(sys, 'frozen', False):
                # After packaging, check _internal beside the executable or the sibling src directory.
                exe_dir = Path(sys.executable).parent
                # Try _internal/assets for PyInstaller onedir builds.
                if (exe_dir / "_internal" / "assets").exists():
                    actual_app_dir = exe_dir / "_internal"
                    mathjax_source_desc = "_internal"
                # Try assets in the PyInstaller onefile extraction directory.
                elif (exe_dir / "assets").exists():
                    actual_app_dir = exe_dir
                    mathjax_source_desc = "exe 同级"
                else:
                    # As a last attempt, walk upward from the executable directory.
                    parent = exe_dir.parent
                    if (parent / "src" / "assets").exists():
                        actual_app_dir = parent / "src"
                        mathjax_source_desc = "父目录 src"
            else:
                # Development mode: use this script directory.
                actual_app_dir = Path(__file__).parent
                mathjax_source_desc = "__file__"
        
        if not actual_app_dir:
            actual_app_dir = Path(APP_DIR) if APP_DIR else Path.cwd()
        
        # Step 2: check the MathJax es5 directory.
        es5_dir = actual_app_dir / "assets" / "MathJax-3.2.2" / "es5"
        tex_chtml = es5_dir / "tex-mml-chtml.js"
        
        if not tex_chtml.exists():
            print(f"[WARN] MathJax 文件缺失: {tex_chtml}")
        
        # Step 3: build the file:// URL.
        # Handle path separators correctly on Windows.
        # QUrl.fromLocalFile needs a normalized path.
        url_path = str(es5_dir).replace("\\", "/")  # Convert to forward slashes.
        if not url_path.endswith("/"):
            url_path += "/"
        
        # Use QUrl.fromLocalFile().
        # QUrl.fromLocalFile() automatically handles the file:// prefix.
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
        # Return a temporary path as a fallback.
        return QUrl.fromLocalFile("/")

def build_math_html(latex_or_list, labels=None) -> str:
    """Build MathJax rendering HTML for a single formula or a formula list."""
    try:
        if isinstance(latex_or_list, str):
            formulas = [latex_or_list] if latex_or_list.strip() else []
        else:
            formulas = [f for f in latex_or_list if f and f.strip()]
        
        if labels is None:
            labels = [None] * len(formulas)
        
        tokens = preview_theme_tokens()

        # Generate MathJax HTML for each formula.
        formula_html = ""
        for i, latex in enumerate(formulas):
            label = labels[i] if i < len(labels) and labels[i] else ""
            label_html = f'<div class="formula-label">{label}</div>' if label else ""
            
            # Render with MathJax; do not HTML-escape LaTeX.
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
        
        # Use the MathJax HTML template with relative paths.
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
        # Return error HTML.
        tokens = preview_theme_tokens()
        return f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"/></head>
    <body style="color: {tokens['error_text']}; background: {tokens['body_bg']}; padding: 20px; font-family: sans-serif;">
<h3>公式渲染出错</h3>
<p><strong>错误信息:</strong> {str(e)}</p>
<p>请检查 MathJax 资源是否正确打包</p>
</body></html>'''
