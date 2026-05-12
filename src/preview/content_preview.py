"""HTML builders for result and history previews."""

from __future__ import annotations

from preview.math_preview import preview_theme_tokens


def build_mixed_content_html(content: str) -> str:
    """Build HTML for mixed text and formula content."""
    import html
    import re
    tokens = preview_theme_tokens()

    # Extract and protect formula segments.
    # Match block formulas $$...$$ first, then inline formulas $...$.
    formula_pattern = r'(\$\$(?:[^$]|\$(?!\$))+?\$\$|\$(?:[^$]|\$(?!\$))+?\$)'

    parts = re.split(formula_pattern, content)
    result_parts = []

    for part in parts:
        if part.startswith('$$') and part.endswith('$$'):
            # Keep block formulas unchanged.
            result_parts.append(part)
        elif part.startswith('$') and part.endswith('$'):
            # Keep inline formulas unchanged.
            result_parts.append(part)
        else:
            # Escape HTML special characters in plain text and preserve line breaks.
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
