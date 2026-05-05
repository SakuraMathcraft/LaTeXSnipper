"""Smart preview HTML builders for formula, text, and mixed content."""

from __future__ import annotations

import html as html_module
import re
from collections.abc import Callable

from preview.math_preview import _preview_theme_tokens, build_math_html
from runtime.config_manager import normalize_content_type


FormulaRenderer = Callable[[str], str]


def build_preview_error_html(error: Exception | str) -> str:
    tokens = _preview_theme_tokens()
    return f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"/></head>
<body style="color: {tokens['error_text']}; background: {tokens['body_bg']}; padding: 20px; font-family: sans-serif;">
<h3>公式渲染失败</h3>
<p><strong>错误:</strong></p>
<pre style="background: {tokens['pre_bg']}; color: {tokens['body_text']}; padding: 10px; border-radius: 4px; overflow-x: auto;">{html_module.escape(str(error))}</pre>
<p><strong>检查项:</strong></p>
<ul>
<li>MathJax 资源是否存在</li>
<li>资源路径是否正确</li>
<li>PyQt6 WebEngine 是否正常工作</li>
</ul>
</body></html>'''


def build_smart_preview_html(items: list, formula_renderer: FormulaRenderer, *, debug: bool = False) -> str:
    """Build the main history/editor preview HTML for mixed content types."""
    try:
        tokens = _preview_theme_tokens()
        if not items:
            return build_math_html("")

        body_content = "\n".join(
            render_content_block(content, label, content_type, formula_renderer, debug=debug)
            for content, label, content_type in items
        )

        mathjax_config = '''
<script>
window.MathJax = {
  tex: {
    inlineMath: [['$','$'], ['\\(','\\)']],
    displayMath: [['$$','$$'], ['\\[','\\]']],
    processEscapes: true
  },
  svg: {
    fontCache: 'global',
    scale: 1
  },
  options: {
    enableMenu: false,
    processHtmlClass: 'formula-content'
  }
};
</script>
<script src="tex-mml-chtml.js" type="text/javascript"></script>'''

        return f'''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
{mathjax_config}
<style>
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    padding: 16px;
    line-height: 1.6;
    background: {tokens['body_bg']};
    color: {tokens['body_text']};
}}
.content-block {{
    margin-bottom: 16px;
    padding: 12px;
    background: {tokens['panel_bg']};
    border-radius: 8px;
    border-left: 4px solid {tokens['border_formula']};
}}
.content-block.text-type {{ border-left-color: {tokens['border_text']}; }}
.content-block.table-type {{ border-left-color: {tokens['border_table']}; }}
.content-block.mixed-type {{ border-left-color: {tokens['border_mixed']}; }}
.block-label {{
    font-size: 12px;
    color: {tokens['muted_text']};
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    gap: 8px;
}}
.type-badge {{
    font-size: 10px;
    padding: 2px 6px;
    border-radius: 4px;
    background: {tokens['badge_formula_bg']};
    color: {tokens['badge_formula_text']};
}}
.type-badge.text {{ background: {tokens['badge_text_bg']}; color: {tokens['badge_text_text']}; }}
.type-badge.table {{ background: {tokens['badge_table_bg']}; color: {tokens['badge_table_text']}; }}
.type-badge.mixed {{ background: {tokens['badge_mixed_bg']}; color: {tokens['badge_mixed_text']}; }}
.block-content {{
    font-size: 14px;
    text-align: center;
}}
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
.formula-content.latex-svg svg {{
    display: block;
    margin: 0 auto;
    max-width: calc(100% / 1.25);
    height: auto;
    transform: scale(1.25);
    transform-origin: center center;
}}
.formula-content.latex-svg {{
    color: {tokens['latex_formula_text']};
    padding-top: 0.25em;
    padding-bottom: 0.25em;
}}
.formula-content.latex-svg svg[fill]:not([fill="none"]),
.formula-content.latex-svg svg *[fill]:not([fill="none"]) {{
    fill: currentColor !important;
}}
.formula-content.latex-svg svg[stroke]:not([stroke="none"]),
.formula-content.latex-svg svg *[stroke]:not([stroke="none"]) {{
    stroke: currentColor !important;
}}
.formula-content.latex-svg svg[style*="fill:"]:not([style*="fill:none"]):not([style*="fill: none"]),
.formula-content.latex-svg svg *[style*="fill:"]:not([style*="fill:none"]):not([style*="fill: none"]) {{
    fill: currentColor !important;
}}
.formula-content.latex-svg svg[style*="stroke:"]:not([style*="stroke:none"]):not([style*="stroke: none"]),
.formula-content.latex-svg svg *[style*="stroke:"]:not([style*="stroke:none"]):not([style*="stroke: none"]) {{
    stroke: currentColor !important;
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
    border: 1px solid {tokens['table_border']};
    padding: 8px;
    text-align: left;
}}
th {{ background-color: {tokens['th_bg']}; }}
.MathJax {{ font-size: 1.4em; }}
.formula-content mjx-container,
.block-content mjx-container {{ font-size: 140% !important; }}
</style>
</head>
<body>{body_content}</body>
</html>'''
    except Exception as exc:
        return build_html_build_error(exc)


def build_html_build_error(error: Exception | str) -> str:
    tokens = _preview_theme_tokens()
    return f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"/></head>
<body style="color: {tokens['error_text']}; background: {tokens['body_bg']}; padding: 20px; font-family: sans-serif;">
<h3>HTML 构建失败</h3>
<p><strong>错误:</strong></p>
<pre style="background: {tokens['pre_bg']}; color: {tokens['body_text']}; padding: 10px; border-radius: 4px; overflow-x: auto;">{html_module.escape(str(error))}</pre>
</body></html>'''


def render_content_block(
    content: str,
    label: str,
    content_type: str,
    formula_renderer: FormulaRenderer,
    *,
    debug: bool = False,
) -> str:
    try:
        content = "" if content is None else str(content)
        label = "" if label is None else str(label)
        content_type = normalize_content_type(str(content_type or "mathcraft"))

        if debug:
            print(f"[RenderBlock] 处理内容块: type={content_type}, label_len={len(label)}, content_len={len(content)}")

        type_name, type_class = {
            "mathcraft": ("公式", ""),
            "mathcraft_text": ("文字", "text"),
            "mathcraft_mixed": ("混合", "mixed"),
        }.get(content_type, ("内容", ""))

        if content_type == "mathcraft":
            rendered_content = formula_renderer(content)
        elif content_type == "mathcraft_mixed":
            rendered_content = render_mixed_content(content)
        else:
            rendered_content = f'<div class="text-content">{html_module.escape(content)}</div>'

        block_class = f"content-block {type_class}-type" if type_class else "content-block"
        badge_class = f"type-badge {type_class}" if type_class else "type-badge"
        result = f'''<div class="{block_class}">
    <div class="block-label">
        <span>{html_module.escape(label or "")}</span>
        <span class="{badge_class}">{type_name}</span>
    </div>
    <div class="block-content">{rendered_content}</div>
</div>'''
        if debug:
            print(f"[RenderBlock] 渲染成功，输出长度: {len(result)}")
        return result
    except Exception as exc:
        print(f"[RenderBlock] 处理内容块失败: {exc}")
        tokens = _preview_theme_tokens()
        error_msg = f"内容块渲染失败: {exc}"
        return (
            f'<div style="color: {tokens["error_text"]}; padding: 10px; '
            f'background: {tokens["error_bg"]}; border-radius: 4px;">{html_module.escape(error_msg)}</div>'
        )


def render_formula_content_html(
    content: str,
    *,
    render_mode: str | None,
    cache_key: str,
    has_cached_svg: bool,
    cached_svg: str,
    namespace_svg_ids: Callable[[str, str], str],
    schedule_render: Callable[[str], None],
) -> str:
    try:
        if render_mode and render_mode.startswith("latex_"):
            if has_cached_svg:
                if cached_svg:
                    safe_svg = namespace_svg_ids(cached_svg, cache_key)
                    return f'<div class="formula-content latex-svg">{safe_svg}</div>'
                return f'<div class="formula-content">$${content}$$</div>'
            schedule_render(content)
        return f'<div class="formula-content">$${content}$$</div>'
    except Exception:
        return f'<div class="formula-content">$${content}$$</div>'


def render_mixed_content(content: str) -> str:
    try:
        if not content:
            return ""

        formula_pattern = r'(\$\$(?:[^$]|\$(?!\$))+?\$\$|\$(?:[^$]|\$(?!\$))+?\$)'
        parts = re.split(formula_pattern, content)
        result_parts = []

        for part in parts:
            if not part:
                continue
            if part.startswith("$$") and part.endswith("$$"):
                result_parts.append(part)
            elif part.startswith("$") and part.endswith("$"):
                result_parts.append(part)
            else:
                result_parts.append(html_module.escape(part).replace("\n", "<br>"))

        return "".join(result_parts)
    except Exception as exc:
        print(f"[RenderMixed] 混合内容渲染失败: {exc}")
        return f'<div style="color: red;">{html_module.escape(f"混合内容渲染失败: {exc}")}</div>'

