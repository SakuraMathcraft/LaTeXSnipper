"""HTML builders for result and history previews."""

from __future__ import annotations

from preview.content_fragments import render_mixed_content
from preview.math_preview import mathjax_loader_script, preview_scrollbar_css, preview_theme_tokens

def build_mixed_content_html(content: str) -> str:
    tokens = preview_theme_tokens()
    body_content = render_mixed_content(content or "")
    loader_script = mathjax_loader_script(scale=1.2)

    return f'''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">

<style>
{preview_scrollbar_css(tokens)}
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
.content > svg {{
   display: block;
   max-width: 100%;
   height: auto;
   margin: 8px auto;
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
<body><div class="content">{body_content}</div>{loader_script}</body>
</html>'''
