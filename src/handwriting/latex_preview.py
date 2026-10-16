from __future__ import annotations

import html

from localization.manager import translate as tr
from preview.content_fragments import render_mixed_content, unwrap_math_delimiters
from preview.math_preview import build_math_html, mathjax_loader_script, preview_scrollbar_css, preview_theme_tokens


def normalize_latex_preview_source(text: str) -> str:
    """Normalize handwritten LaTeX without splitting multi-line environments."""
    return unwrap_math_delimiters(str(text or "").replace("\r\n", "\n").strip())


def build_handwriting_preview_html(text: str, output_mode: str = "latex") -> str:
    mode = str(output_mode or "latex").strip().lower()
    content = str(text or "").replace("\r\n", "\n").strip()
    if mode == "markdown":
        return _build_markdown_math_html(content)
    if mode != "latex":
        return _build_plain_text_html(content)
    return build_math_html(normalize_latex_preview_source(content), center_viewport=not content)


def _build_markdown_math_html(content: str) -> str:
    tokens = preview_theme_tokens()
    body = (
        render_mixed_content(content)
        if content
        else f'<div class="empty">{html.escape(tr("写完后会在这里看到预览"))}</div>'
    )
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    {preview_scrollbar_css(tokens)}
    html, body {{
      margin: 0;
      padding: 0;
      min-height: 100%;
      background: {tokens["body_bg"]};
      color: {tokens["body_text"]};
      overflow: auto;
      font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
    }}
    body {{
      box-sizing: border-box;
      padding: 16px;
      line-height: 1.6;
      font-size: 18px;
    }}
    .content {{
      min-height: 100%;
    }}
    .content > svg {{ display: block; max-width: 100%; height: auto; margin: 8px auto; }}
    .empty {{
      min-height: 220px;
      display: flex;
      align-items: center;
      justify-content: center;
      color: {tokens["muted_text"]};
    }}
    mjx-container[display="true"] {{
      margin: 0.35em 0 !important;
    }}
  </style>
  {mathjax_loader_script()}
</head>
<body><div class="content">{body}</div></body>
</html>"""


def _build_plain_text_html(content: str) -> str:
    tokens = preview_theme_tokens()
    body = html.escape(content) if content else html.escape(tr("写完后会在这里看到预览"))
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    html, body {{
      margin: 0;
      padding: 0;
      min-height: 100%;
      background: {tokens["body_bg"]};
      color: {tokens["body_text"]};
      overflow: auto;
      font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
    }}
    body {{
      box-sizing: border-box;
      padding: 16px;
      white-space: pre-wrap;
      word-break: break-word;
      overflow-wrap: anywhere;
      line-height: 1.55;
      font-size: 18px;
    }}
  </style>
</head>
<body>{body}</body>
</html>"""
