"""HTML builders for result and history previews."""

from __future__ import annotations

import html
import re

from preview.math_preview import mathjax_loader_script, preview_theme_tokens

FORMULA_PATTERN = re.compile(r"(\$\$(?:[^$]|\$(?!\$))+?\$\$|\$(?:[^$]|\$(?!\$))+?\$)")


def _mixed_content_body(content: str) -> str:
    parts = FORMULA_PATTERN.split(content or "")
    result_parts = []

    for part in parts:
        if (part.startswith("$$") and part.endswith("$$")) or (part.startswith("$") and part.endswith("$")):
            result_parts.append(part)
        else:
            result_parts.append(html.escape(part).replace("\n", "<br>"))

    return "".join(result_parts)


def build_mixed_content_html(content: str) -> str:
    tokens = preview_theme_tokens()
    body_content = _mixed_content_body(content)
    loader_script = mathjax_loader_script()

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
<body><div class="content">{body_content}</div>{loader_script}</body>
</html>'''
