"""HTML builders for result and history previews."""

from __future__ import annotations

import html
import re

from preview.math_preview import (
    mathjax_loader_script,
    preview_scrollbar_css,
    preview_theme_tokens,
)

FORMULA_PATTERN = re.compile(r"(\$\$(?:[^$]|\$(?!\$))+?\$\$|\$(?:[^$]|\$(?!\$))+?\$)")


def render_mixed_content(content: str) -> str:
    parts = FORMULA_PATTERN.split(content or "")
    result_parts = []

    for part in parts:
        if (part.startswith("$$") and part.endswith("$$")) or (
            part.startswith("$") and part.endswith("$")
        ):
            result_parts.append(part)
        else:
            result_parts.append(html.escape(part).replace("\n", "<br>"))

    return "".join(result_parts)


def mixed_content_css(tokens: dict) -> str:
    return f"""
.mixed-content {{
   font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
   font-size: 14px;
   line-height: 1.8;
   text-align: left;
}}
.mixed-content br {{
   line-height: 1.8;
}}
.mixed-content .MathJax, .mixed-content mjx-container {{
   font-size: 1.45em !important;
   color: {tokens["body_text"]} !important;
}}
.mixed-content a {{
   color: {tokens["label_text"]};
}}
.mixed-content pre, .mixed-content code {{
   background: {tokens["pre_bg"]};
   color: {tokens["body_text"]};
   border-radius: 6px;
}}
"""


def build_mixed_content_html(content: str) -> str:
    tokens = preview_theme_tokens()
    body_content = render_mixed_content(content)
    loader_script = mathjax_loader_script(scale=1.2)

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">

<style>
{preview_scrollbar_css(tokens)}
html, body {{
   margin: 0;
   padding: 0;
   background: {tokens["body_bg"]};
   color: {tokens["body_text"]};
}}
body {{
   padding: 16px;
}}
.content {{
   min-height: calc(100vh - 32px);
background: transparent;
border: none;
border-radius: 0;
padding: 0;
   box-sizing: border-box;
}}
{mixed_content_css(tokens)}
</style>
</head>
<body><div class="content mixed-content">{body_content}</div>{loader_script}</body>
</html>"""
