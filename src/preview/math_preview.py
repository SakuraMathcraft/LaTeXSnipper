"""MathJax preview HTML and theme tokens."""

from __future__ import annotations

from pathlib import Path
import sys

from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import QApplication

APP_DIR: Path | None = None

MATHJAX_CDN_URL = "https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-mml-chtml.js"
MATHJAX_CDN_URL_BACKUP = "https://cdnjs.cloudflare.com/ajax/libs/mathjax/3.2.2/es5/tex-mml-chtml.js"

_MATHJAX_LOGGED_KEYS: set[str] = set()


def configure_math_preview_runtime(app_dir: Path | str | None) -> None:
    global APP_DIR
    APP_DIR = Path(app_dir) if app_dir else None


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


def mathjax_loader_script(*, log_local_fallback: bool = False) -> str:
    should_log = "true" if log_local_fallback else "false"
    return f"""<script>
(function() {{
  var shouldLogLocalFallback = {should_log};
  var localScript = 'tex-mml-chtml.js';
  var cdnUrls = ['{MATHJAX_CDN_URL}', '{MATHJAX_CDN_URL_BACKUP}'];
  function appendScript(node) {{
    var target = document.body || document.head || document.documentElement;
    if (target) {{
      target.appendChild(node);
    }}
  }}
  var script = document.createElement('script');
  script.type = 'text/javascript';
  script.async = true;
  script.onerror = function() {{
    if (shouldLogLocalFallback) {{
      console.warn('[MathJax] local MathJax failed, trying CDN...');
    }}
    var cdnScript = document.createElement('script');
    cdnScript.src = cdnUrls[0];
    cdnScript.type = 'text/javascript';
    cdnScript.async = true;
    cdnScript.onerror = function() {{
      var backupScript = document.createElement('script');
      backupScript.src = cdnUrls[1];
      backupScript.type = 'text/javascript';
      backupScript.async = true;
      appendScript(backupScript);
    }};
    appendScript(cdnScript);
  }};
  script.src = localScript;
  appendScript(script);
}})();
</script>"""


MATHJAX_HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
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
body.viewport-centered {
  min-height: calc(100vh - 24px);
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: center;
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
body.viewport-centered .math-container {
  min-height: calc(100vh - 24px);
  margin-bottom: 0;
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
<body class="__BODY_CLASS__">
__FORMULAS__
__MATHJAX_LOADER_SCRIPT__
</body>
</html>
"""


def _current_render_mode() -> str:
    try:
        from backend.latex_renderer import _latex_settings

        return _latex_settings.get_render_mode() if _latex_settings else "auto"
    except Exception as exc:
        print(f"[WARN] 获取渲染模式失败: {exc}")
    return "auto"


def _mathjax_base_dir() -> tuple[Path, str]:
    if APP_DIR and str(APP_DIR).strip():
        return Path(APP_DIR), "本地资源"

    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        meipass = getattr(sys, "_MEIPASS", "")
        candidates = [
            (exe_dir / "_internal", "_internal"),
            (exe_dir, "exe 同级"),
            (exe_dir.parent / "src", "父目录 src"),
        ]
        if meipass:
            candidates.insert(0, (Path(meipass), "_MEIPASS"))
        for candidate, label in candidates:
            if candidate and (candidate / "assets").exists():
                return candidate, label

    return Path(__file__).resolve().parents[1], "__file__"


def get_mathjax_base_url() -> QUrl:
    """Return the MathJax base URL used by setHtml."""
    try:
        mode = _current_render_mode()
        if mode == "mathjax_cdn":
            if "cdn" not in _MATHJAX_LOGGED_KEYS:
                print("[MathJax] 使用 CDN MathJax")
                _MATHJAX_LOGGED_KEYS.add("cdn")
            return QUrl(MATHJAX_CDN_URL.rsplit("/", 1)[0] + "/")

        if mode.startswith("latex_"):
            mode_key = f"latex:{mode}"
            if mode_key not in _MATHJAX_LOGGED_KEYS:
                print(f"[MathJax] LaTeX 模式下仍使用本地 MathJax base: {mode}")
                _MATHJAX_LOGGED_KEYS.add(mode_key)

        actual_app_dir, source_desc = _mathjax_base_dir()
        es5_dir = actual_app_dir / "assets" / "MathJax-3.2.2" / "es5"
        tex_chtml = es5_dir / "tex-mml-chtml.js"
        if not tex_chtml.exists():
            print(f"[WARN] MathJax 文件缺失: {tex_chtml}")

        url = QUrl.fromLocalFile(str(es5_dir) + "/")
        url_str = url.toString()
        if not url_str.startswith("file:///"):
            print(f"[ERROR] URL 格式异常，应以 file:/// 开头: {url_str}")
        else:
            local_key = f"local:{source_desc}:{url_str}"
            if local_key not in _MATHJAX_LOGGED_KEYS:
                label = "使用本地资源" if source_desc == "本地资源" else f"使用本地资源({source_desc})"
                print(f"[MathJax] {label}: {url_str}")
                _MATHJAX_LOGGED_KEYS.add(local_key)

        return url
    except Exception as exc:
        print(f"[ERROR] get_mathjax_base_url 异常: {exc}")
        import traceback

        traceback.print_exc()
        return QUrl.fromLocalFile("/")


def build_math_html(latex_or_list, labels=None, *, center_viewport: bool = False) -> str:
    """Build MathJax rendering HTML for a single formula or a formula list."""
    try:
        if isinstance(latex_or_list, str):
            formulas = [latex_or_list] if latex_or_list.strip() else []
        else:
            formulas = [f for f in latex_or_list if f and f.strip()]

        if labels is None:
            labels = [None] * len(formulas)

        tokens = preview_theme_tokens()
        formula_html = ""
        for i, latex in enumerate(formulas):
            label = labels[i] if i < len(labels) and labels[i] else ""
            label_html = f'<div class="formula-label">{label}</div>' if label else ""
            formula_html += f'<div class="math-container">{label_html}<div class="formula-content">$${latex}$$</div></div>\n'

        if not formula_html:
            formula_html = f'<div class="math-container" style="color:{tokens["muted_text"]};">无公式</div>'

        mode = _current_render_mode()
        log_local_fallback = mode in ("auto", "mathjax_local")
        html = MATHJAX_HTML_TEMPLATE.replace("__FORMULAS__", formula_html)
        replacements = {
            "__MATHJAX_LOADER_SCRIPT__": mathjax_loader_script(log_local_fallback=log_local_fallback),
            "__BODY_CLASS__": "viewport-centered" if center_viewport else "",
            "__BODY_BG__": tokens["body_bg"],
            "__BODY_TEXT__": tokens["body_text"],
            "__LABEL_TEXT__": tokens["label_text"],
            "__LABEL_BG__": tokens["label_bg"],
            "__ERROR_TEXT__": tokens["error_text"],
            "__ERROR_BG__": tokens["error_bg"],
        }
        for key, value in replacements.items():
            html = html.replace(key, value)
        return html
    except Exception as exc:
        print(f"[ERROR] build_math_html 出错: {exc}")
        import traceback

        traceback.print_exc()
        tokens = preview_theme_tokens()
        return f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"/></head>
<body style="color: {tokens['error_text']}; background: {tokens['body_bg']}; padding: 20px; font-family: sans-serif;">
<h3>公式渲染出错</h3>
<p><strong>错误信息:</strong> {str(exc)}</p>
<p>请检查 MathJax 资源是否正确打包</p>
</body></html>'''
