from __future__ import annotations

import html
import re

from preview.math_preview import build_math_html, mathjax_loader_script, preview_scrollbar_css, preview_theme_tokens


_FENCED_BLOCK_RE = re.compile(
    r"```(?:latex|tex|math)?\s*(.*?)\s*```",
    flags=re.IGNORECASE | re.DOTALL,
)


def unwrap_math_delimiters(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return ""

    fence_match = _FENCED_BLOCK_RE.fullmatch(value)
    if fence_match:
        value = fence_match.group(1).strip()

    for left, right in (("$$", "$$"), (r"\[", r"\]"), (r"\(", r"\)"), ("$", "$")):
        if value.startswith(left) and value.endswith(right):
            inner = value[len(left) : len(value) - len(right)].strip()
            if inner:
                return inner
    return value


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
    body = _render_markdown_math_content(content) if content else '<div class="empty">写完后会在这里看到预览</div>'
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
      display: flex;
      flex-direction: column;
      gap: 10px;
      align-items: stretch;
      min-height: 100%;
    }}
    .text-line {{
      white-space: pre-wrap;
      word-break: break-word;
      overflow-wrap: anywhere;
    }}
    .math-line {{
      overflow-x: auto;
      text-align: center;
      padding: 4px 0;
    }}
    .spacer {{ height: 6px; }}
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
  <script>
    window.MathJax = {{
      tex: {{
        inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
        displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']],
        processEscapes: true
      }},
      svg: {{ fontCache: 'global' }},
      options: {{ enableMenu: false }}
    }};
  </script>
  {mathjax_loader_script()}
</head>
<body><div class="content">{body}</div></body>
</html>"""


def _render_markdown_math_content(content: str) -> str:
    blocks: list[str] = []
    parts = re.split(r"(\$\$.*?\$\$)", content, flags=re.DOTALL)
    for part in parts:
        if not part:
            continue
        if part.startswith("$$") and part.endswith("$$"):
            blocks.append(f'<div class="math-line">{part}</div>')
            continue
        for raw_line in part.split("\n"):
            line = raw_line.strip()
            if not line:
                if blocks and blocks[-1] != '<div class="spacer"></div>':
                    blocks.append('<div class="spacer"></div>')
                continue
            blocks.append(f'<div class="text-line">{html.escape(line)}</div>')
    return "".join(blocks)


def _build_plain_text_html(content: str) -> str:
    tokens = preview_theme_tokens()
    body = html.escape(content) if content else "写完后会在这里看到预览"
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
