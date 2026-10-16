"""MathJax preview HTML and theme tokens."""

from __future__ import annotations

import logging

from localization.manager import translate as tr
from preview.content_fragments import render_formula_content
from PyQt6.QtCore import QUrl

from rendering.mathjax_runtime import ASSET_ROOT, loader_script
from ui.theme_tokens import is_dark_ui

logger = logging.getLogger(f"latexsnipper.{__name__}")


def preview_theme_tokens() -> dict:
    if is_dark_ui():
        return {
            "body_bg": "#14171d",
            "body_text": "#e8ebf0",
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
            "scrollbar_track": "#1b1f27",
            "scrollbar_thumb": "#6f7782",
            "scrollbar_thumb_hover": "#8b949e",
        }
    return {
        "body_bg": "#fafafa",
        "body_text": "#1f2328",
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
        "scrollbar_track": "#f0f0f0",
        "scrollbar_thumb": "#b8b8b8",
        "scrollbar_thumb_hover": "#969696",
    }


def preview_scrollbar_css(tokens: dict) -> str:
    scheme = "dark" if is_dark_ui() else "light"
    return f"""
html {{
  color-scheme: {scheme};
  scrollbar-color: {tokens["scrollbar_thumb"]} {tokens["scrollbar_track"]};
}}
::-webkit-scrollbar {{
  width: 10px;
  height: 10px;
  background: {tokens["scrollbar_track"]};
}}
::-webkit-scrollbar-thumb {{
  background: {tokens["scrollbar_thumb"]};
  border-radius: 0;
}}
::-webkit-scrollbar-thumb:hover {{
  background: {tokens["scrollbar_thumb_hover"]};
}}
::-webkit-scrollbar-corner {{
  background: {tokens["scrollbar_track"]};
}}
"""


def mathjax_loader_script(*, scale: float = 1, options: dict | None = None) -> str:
    return loader_script(scale=scale, options=options)


MATHJAX_HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<meta http-equiv="Content-Security-Policy" content="default-src * 'unsafe-inline' 'unsafe-eval' data: blob: file:; script-src * 'unsafe-inline' 'unsafe-eval'; style-src * 'unsafe-inline';">
<style>
__SCROLLBAR_CSS__
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
.document-content {
  width: 100%;
  text-align: left;
  overflow-wrap: anywhere;
}
.document-content > svg {
  display: block;
  max-width: 100%;
  height: auto;
  margin: 8px auto;
}
.error-text {
  color: __ERROR_TEXT__;
  font-size: 12px;
  padding: 8px;
  background: __ERROR_BG__;
  border-radius: 4px;
}
</style>

</head>
<body class="__BODY_CLASS__">
__FORMULAS__
__MATHJAX_LOADER_SCRIPT__
</body>
</html>
"""


def get_mathjax_base_url() -> QUrl:
    """Return the bundled runtime URL for every desktop preview."""
    return QUrl.fromLocalFile(str(ASSET_ROOT) + "/")


def build_math_html(
    latex_or_list, labels=None, *, center_viewport: bool = False
) -> str:
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
            formula_html += f'<div class="math-container">{label_html}{render_formula_content(latex)}</div>\n'

        if not formula_html:
            formula_html = (
                f'<div class="math-container" style="color:{tokens["muted_text"]};">'
                f'{tr("无公式")}</div>'
            )

        html = MATHJAX_HTML_TEMPLATE.replace("__FORMULAS__", formula_html)
        replacements = {
            "__MATHJAX_LOADER_SCRIPT__": mathjax_loader_script(
                scale=1.15
            ),
            "__BODY_CLASS__": "viewport-centered" if center_viewport else "",
            "__SCROLLBAR_CSS__": preview_scrollbar_css(tokens),
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
        logger.exception("构建公式预览页面失败: %s", exc)
        tokens = preview_theme_tokens()
        title = tr("公式渲染出错")
        error_label = tr("错误信息:")
        hint = tr("请检查 MathJax 资源是否正确打包")
        return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/></head>
<body style="color: {tokens["error_text"]}; background: {tokens["body_bg"]}; padding: 20px; font-family: sans-serif;">
<h3>{title}</h3>
<p><strong>{error_label}</strong> {str(exc)}</p>
<p>{hint}</p>
</body></html>"""
