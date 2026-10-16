"""Smart preview HTML builders for formula, text, and mixed content."""

from __future__ import annotations

import logging
import html as html_module

from localization.manager import translate as tr
from preview.content_fragments import render_formula_content, render_mixed_content
from preview.math_preview import (
    build_math_html,
    mathjax_loader_script,
    preview_scrollbar_css,
    preview_theme_tokens,
)
from runtime.content_types import normalize_content_type

logger = logging.getLogger(f"latexsnipper.{__name__}")


def build_preview_error_html(error: Exception | str) -> str:
    tokens = preview_theme_tokens()
    title = html_module.escape(tr("公式渲染失败"))
    error_label = html_module.escape(tr("错误:"))
    checklist_label = html_module.escape(tr("检查项:"))
    checklist = (
        tr("MathJax 资源是否存在"),
        tr("资源路径是否正确"),
        tr("PyQt6 WebEngine 是否正常工作"),
    )
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/></head>
<body style="color: {tokens["error_text"]}; background: {tokens["body_bg"]}; padding: 20px; font-family: sans-serif;">
<h3>{title}</h3>
<p><strong>{error_label}</strong></p>
<pre style="background: {tokens["pre_bg"]}; color: {tokens["body_text"]}; padding: 10px; border-radius: 4px; overflow-x: auto;">{html_module.escape(str(error))}</pre>
<p><strong>{checklist_label}</strong></p>
<ul>
<li>{html_module.escape(checklist[0])}</li>
<li>{html_module.escape(checklist[1])}</li>
<li>{html_module.escape(checklist[2])}</li>
</ul>
</body></html>"""


def build_smart_preview_html(items: list) -> str:
    """Build the main history/editor preview HTML for mixed content types."""
    try:
        tokens = preview_theme_tokens()
        if not items:
            return build_math_html("", center_viewport=True)

        body_content = "\n".join(
            render_content_block(content, label, content_type)
            for content, label, content_type in items
        )

        mathjax_config = mathjax_loader_script(options={"processHtmlClass": "formula-content"})

        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
{mathjax_config}
<style>
{preview_scrollbar_css(tokens)}
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    padding: 16px;
    line-height: 1.6;
    background: {tokens["body_bg"]};
    color: {tokens["body_text"]};
}}
.content-block {{
    margin-bottom: 16px;
    padding: 12px;
    background: {tokens["panel_bg"]};
    border-radius: 8px;
    border-left: 4px solid {tokens["border_formula"]};
}}
.content-block.text-type {{ border-left-color: {tokens["border_text"]}; }}
.content-block.table-type {{ border-left-color: {tokens["border_table"]}; }}
.content-block.mixed-type {{ border-left-color: {tokens["border_mixed"]}; }}
.block-label {{
    font-size: 12px;
    color: {tokens["muted_text"]};
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    gap: 8px;
}}
.type-badge {{
    font-size: 10px;
    padding: 2px 6px;
    border-radius: 4px;
    background: {tokens["badge_formula_bg"]};
    color: {tokens["badge_formula_text"]};
}}
.type-badge.text {{ background: {tokens["badge_text_bg"]}; color: {tokens["badge_text_text"]}; }}
.type-badge.table {{ background: {tokens["badge_table_bg"]}; color: {tokens["badge_table_text"]}; }}
.type-badge.mixed {{ background: {tokens["badge_mixed_bg"]}; color: {tokens["badge_mixed_text"]}; }}
.block-content {{
    font-size: 14px;
    text-align: center;
}}
.document-content {{ text-align: left; overflow-wrap: anywhere; }}
.document-content > svg {{ display: block; max-width: 100%; height: auto; margin: 8px auto; }}
.formula-content {{
    text-align: center;
    padding: 0.15em 0.35em;
    margin: 0.05em 0;
    display: inline-block;
    max-width: 100%;
    box-sizing: border-box;
}}
.formula-content img,
.formula-content svg {{
    max-width: 100%;
    height: auto;
    vertical-align: middle;
    display: block;
    margin: 0 auto;
}}
.text-content {{
    white-space: pre-wrap;
    word-wrap: break-word;
}}
table {{
    border-collapse: collapse;
    width: 100%;
    margin: 8px 0;
}}
th, td {{
    border: 1px solid {tokens["table_border"]};
    padding: 8px;
    text-align: left;
}}
th {{ background-color: {tokens["th_bg"]}; }}
.MathJax {{ font-size: 1.4em; }}
.formula-content mjx-container,
.block-content mjx-container {{ font-size: 140% !important; }}
</style>
</head>
<body>{body_content}</body>
</html>"""
    except Exception as exc:
        return build_html_build_error(exc)


def build_html_build_error(error: Exception | str) -> str:
    tokens = preview_theme_tokens()
    title = html_module.escape(tr("HTML 构建失败"))
    error_label = html_module.escape(tr("错误:"))
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/></head>
<body style="color: {tokens["error_text"]}; background: {tokens["body_bg"]}; padding: 20px; font-family: sans-serif;">
<h3>{title}</h3>
<p><strong>{error_label}</strong></p>
<pre style="background: {tokens["pre_bg"]}; color: {tokens["body_text"]}; padding: 10px; border-radius: 4px; overflow-x: auto;">{html_module.escape(str(error))}</pre>
</body></html>"""


def render_content_block(
    content: str,
    label: str,
    content_type: str,
) -> str:
    try:
        content = "" if content is None else str(content)
        label = "" if label is None else str(label)
        content_type = normalize_content_type(content_type)

        type_name, type_class = {
            "mathcraft": (tr("公式"), ""),
            "mathcraft_text": (tr("文字"), "text"),
            "mathcraft_mixed": (tr("混合"), "mixed"),
        }[content_type]

        if content_type == "mathcraft":
            rendered_content = render_formula_content(content)
        elif content_type == "mathcraft_mixed":
            rendered_content = f'<div class="document-content">{render_mixed_content(content)}</div>'
        else:
            rendered_content = (
                f'<div class="text-content">{html_module.escape(content)}</div>'
            )

        block_class = (
            f"content-block {type_class}-type" if type_class else "content-block"
        )
        badge_class = f"type-badge {type_class}" if type_class else "type-badge"
        result = f'''<div class="{block_class}">
    <div class="block-label">
        <span>{html_module.escape(label or "")}</span>
        <span class="{badge_class}">{type_name}</span>
    </div>
    <div class="block-content">{rendered_content}</div>
</div>'''
        return result
    except Exception as exc:
        logger.warning("预览内容块渲染失败: %s", exc)
        tokens = preview_theme_tokens()
        error_msg = tr("内容块渲染失败: {error}").format(error=exc)
        return (
            f'<div style="color: {tokens["error_text"]}; padding: 10px; '
            f'background: {tokens["error_bg"]}; border-radius: 4px;">{html_module.escape(error_msg)}</div>'
        )
