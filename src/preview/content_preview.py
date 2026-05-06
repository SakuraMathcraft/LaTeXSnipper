"""HTML builders for result and history previews."""

from __future__ import annotations

from preview.math_preview import preview_theme_tokens


def build_mixed_content_html(content: str) -> str:
    """构建混合内容（文字+公式）的 HTML"""
    import html
    import re
    tokens = preview_theme_tokens()

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
