"""HTML builders for result and history previews."""

from __future__ import annotations

from preview.math_preview import _preview_theme_tokens


def build_mixed_content_html(content: str) -> str:
    """构建混合内容（文字+公式）的 HTML"""
    import html
    import re
    tokens = _preview_theme_tokens()

    # 提取并保护公式部分
    # 先匹配块级公式 $$...$$，再匹配行内公式 $...$
    formula_pattern = r'(\$\$(?:[^$]|\$(?!\$))+?\$\$|\$(?:[^$]|\$(?!\$))+?\$)'

    parts = re.split(formula_pattern, content)
    result_parts = []

    for part in parts:
        if part.startswith('$$') and part.endswith('$$'):
            # 块级公式，保持原样
            result_parts.append(part)
        elif part.startswith('$') and part.endswith('$'):
            # 行内公式，保持原样
            result_parts.append(part)
        else:
            # 普通文本，转义 HTML 特殊字符，保留换行
            escaped = html.escape(part)
            escaped = escaped.replace('\n', '<br>')
            result_parts.append(escaped)

    body_content = ''.join(result_parts)

    return f'''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<script>
  window.MathJax = {{
tex: {{
  inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
  displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']],
  processEscapes: true
}},
svg: {{
  fontCache: 'global',
        scale: 1.2
}},
options: {{
  enableMenu: false,
  skipHtmlTags: [],
  ignoreHtmlClass: [],
  processHtmlClass: []
}}
  }};
</script>
<script src="tex-mml-chtml.js" async></script>
<style>
html, body {{
   margin: 0;
   padding: 0;
   background: {tokens['body_bg']};
   color: {tokens['body_text']};
}}
body {{
   font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
   padding: 16px;
   line-height: 1.8;
   font-size: 14px;
}}
.content {{
   min-height: calc(100vh - 32px);
background: transparent;
border: none;
border-radius: 0;
padding: 0;
   box-sizing: border-box;
}}
.content br {{
   line-height: 1.8;
}}
.MathJax, .mjx-container {{
font-size: 1.45em !important;
   color: {tokens['body_text']} !important;
}}
a {{
   color: {tokens['label_text']};
}}
pre, code {{
   background: {tokens['pre_bg']};
   color: {tokens['body_text']};
   border-radius: 6px;
}}
</style>
</head>
<body><div class="content">{body_content}</div></body>
</html>'''


def build_mixed_preview_html(formulas: list, labels: list) -> str:
    """构建混合模式的预览 HTML（支持多个公式）"""
    import html
    import re
    tokens = _preview_theme_tokens()

    items_html = []
    for i, (formula, label) in enumerate(zip(formulas, labels)):
        # 提取并保护公式部分
        # 先匹配块级公式 $$...$$，再匹配行内公式 $...$
        formula_pattern = r'(\$\$(?:[^$]|\$(?!\$))+?\$\$|\$(?:[^$]|\$(?!\$))+?\$)'
        parts = re.split(formula_pattern, formula)
        result_parts = []

        for part in parts:
            if part.startswith('$$') and part.endswith('$$'):
                result_parts.append(part)
            elif part.startswith('$') and part.endswith('$'):
                result_parts.append(part)
            else:
                escaped = html.escape(part)
                escaped = escaped.replace('\n', '<br>')
                result_parts.append(escaped)

        body_content = ''.join(result_parts)
        label_html = f'<span class="label">#{i+1} {html.escape(label)}</span>' if label else f'<span class="label">#{i+1}</span>'
        items_html.append(f'<div class="item">{label_html}<div class="content">{body_content}</div></div>')

    return f'''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<script>
window.MathJax = {{
    tex: {{
        inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
        displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']],
        processEscapes: true
    }},
    svg: {{
        fontCache: 'global',
        scale: 1.15
    }},
    options: {{
        enableMenu: false,
        skipHtmlTags: [],
        ignoreHtmlClass: [],
        processHtmlClass: []
    }}
}};
</script>
<script src="es5/tex-mml-chtml.js" async></script>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; padding: 16px; background: {tokens['body_bg']}; color: {tokens['body_text']}; }}
.item {{ margin-bottom: 16px; padding: 12px; background: {tokens['panel_bg']}; border: 1px solid {tokens['table_border']}; border-radius: 8px; }}
.label {{ display: inline-block; background: {tokens['border_formula']}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px; margin-bottom: 8px; }}
.content {{ line-height: 1.8; font-size: 14px; }}
.MathJax, .mjx-container {{ font-size: 1.45em !important; color: {tokens['body_text']} !important; }}
</style>
</head>
<body>{"".join(items_html) if items_html else f"<p style='color:{tokens['muted_text']};'>暂无内容</p>"}</body>
</html>'''


def build_text_preview_html(formulas: list, labels: list) -> str:
    """构建纯文本模式的预览 HTML"""
    import html
    tokens = _preview_theme_tokens()

    items_html = []
    for i, (formula, label) in enumerate(zip(formulas, labels)):
        escaped = html.escape(formula).replace('\n', '<br>')
        label_html = f'<span class="label">#{i+1} {html.escape(label)}</span>' if label else f'<span class="label">#{i+1}</span>'
        items_html.append(f'<div class="item">{label_html}<div class="content">{escaped}</div></div>')

    return f'''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; padding: 16px; background: {tokens['body_bg']}; color: {tokens['body_text']}; }}
.item {{ margin-bottom: 16px; padding: 12px; background: {tokens['panel_bg']}; border: 1px solid {tokens['table_border']}; border-radius: 8px; }}
.label {{ display: inline-block; background: {tokens['border_text']}; color: {tokens['body_bg']}; padding: 2px 8px; border-radius: 4px; font-size: 12px; margin-bottom: 8px; }}
.content {{ line-height: 1.6; font-size: 14px; white-space: pre-wrap; }}
</style>
</head>
<body>{"".join(items_html) if items_html else f"<p style='color:{tokens['muted_text']};'>暂无内容</p>"}</body>
</html>'''


def build_table_preview_html(formulas: list, labels: list) -> str:
    """构建表格模式的预览 HTML"""
    import html
    tokens = _preview_theme_tokens()

    items_html = []
    for i, (formula, label) in enumerate(zip(formulas, labels)):
        # 如果是 HTML 表格，直接使用；否则显示为代码
        if formula.strip().startswith('<'):
            content = formula
        else:
            content = f"<pre>{html.escape(formula)}</pre>"

        label_html = f'<span class="label">#{i+1} {html.escape(label)}</span>' if label else f'<span class="label">#{i+1}</span>'
        items_html.append(f'<div class="item">{label_html}<div class="content">{content}</div></div>')

    return f'''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; padding: 16px; background: {tokens['body_bg']}; color: {tokens['body_text']}; }}
.item {{ margin-bottom: 16px; padding: 12px; background: {tokens['panel_bg']}; border: 1px solid {tokens['table_border']}; border-radius: 8px; }}
.label {{ display: inline-block; background: {tokens['border_table']}; color: {tokens['body_bg']}; padding: 2px 8px; border-radius: 4px; font-size: 12px; margin-bottom: 8px; }}
.content {{ font-size: 14px; overflow-x: auto; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid {tokens['table_border']}; padding: 8px; text-align: left; }}
th {{ background-color: {tokens['th_bg']}; }}
pre {{ white-space: pre-wrap; word-wrap: break-word; margin: 0; }}
</style>
</head>
<body>{"".join(items_html) if items_html else f"<p style='color:{tokens['muted_text']};'>暂无内容</p>"}</body>
</html>'''


def build_table_html(content: str) -> str:
    """构建表格的 HTML 预览"""
    tokens = _preview_theme_tokens()
    # 如果内容已经是 HTML 格式，直接使用
    if content.strip().startswith('<'):
        table_content = content
    else:
        # 尝试将 Markdown 表格转为 HTML
        import html
        table_content = f"<pre>{html.escape(content)}</pre>"

    return f'''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
   padding: 16px; background: {tokens['body_bg']}; color: {tokens['body_text']}; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid {tokens['table_border']}; padding: 8px; text-align: left; }}
th {{ background-color: {tokens['th_bg']}; }}
tr:nth-child(even) {{ background-color: {tokens['panel_bg']}; }}
pre {{ white-space: pre-wrap; word-wrap: break-word; }}
</style>
</head>
<body>{table_content}</body>
</html>'''
