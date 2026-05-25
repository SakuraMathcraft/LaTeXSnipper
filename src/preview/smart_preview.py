"""Smart preview HTML builders for formula, text, and mixed content."""

from __future__ import annotations

import html as html_module
import re
from collections.abc import Callable


from backend.typst_utils import looks_like_latex_math, clean_pandoc_typst_artifacts


from preview.math_preview import build_math_html, mathjax_loader_script, preview_scrollbar_css, preview_theme_tokens

from runtime.config_manager import normalize_content_type


FormulaRenderer = Callable[[str], str]


def build_preview_error_html(error: Exception | str) -> str:
    tokens = preview_theme_tokens()
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
        tokens = preview_theme_tokens()
        if not items:
            return build_math_html("")

        body_content = "\n".join(
            render_content_block(content, label, content_type, formula_renderer, debug=debug)
            for content, label, content_type in items
        )

        mathjax_config = f'''
<script>
window.MathJax = {{
  tex: {{
    inlineMath: [['$','$'], ['\\(','\\)']],
    displayMath: [['$$','$$'], ['\\[','\\]']],
    processEscapes: true
  }},
  svg: {{
    fontCache: 'global',
    scale: 1
  }},
  options: {{
    enableMenu: false,
    processHtmlClass: 'formula-content'
  }}
}};
</script>
{mathjax_loader_script()}'''

        return f'''<!DOCTYPE html>
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
.render-mode-badge {{
    font-size: 10px;
    padding: 2px 6px;
    border-radius: 4px;
    background: {tokens['label_bg']};
    color: {tokens['label_text']};
    font-weight: 600;
}}
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
.typst-raw-content {{
    display: block;
    padding: 8px 12px;
    font-family: "Cascadia Code", "Fira Code", "JetBrains Mono", Consolas, monospace;
    font-size: 13px;
    color: {tokens['muted_text']};
    background: {tokens['pre_bg']};
    border-radius: 4px;
    text-align: left;
    white-space: pre-wrap;
    word-break: break-all;
    border: 1px dashed {tokens['table_border']};
}}
.formula-content.latex-svg {{
    color: {tokens['latex_formula_text']};
    padding-top: 0.25em;
    padding-bottom: 0.25em;
}}
/* Make Typst/LaTeX SVG glyphs inherit the theme text colour.  The
   Python-side _clean_typst_svg() already strips hardcoded fill/stroke
   attributes; these rules are defence-in-depth for any remaining cases. */
.formula-content.latex-svg svg {{
    color: inherit;
    background: transparent;
}}
.formula-content.latex-svg svg path {{
    fill: currentColor !important;
    stroke: currentColor !important;
}}
.formula-content.latex-svg svg text {{
    fill: currentColor !important;
    stroke: currentColor !important;
}}
.formula-content.latex-svg svg use {{
    fill: currentColor !important;
    stroke: currentColor !important;
}}
.formula-content.latex-svg svg g {{
    fill: currentColor !important;
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
    tokens = preview_theme_tokens()
    return f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"/></head>
<body style="color: {tokens['error_text']}; background: {tokens['body_bg']}; padding: 20px; font-family: sans-serif;">
<h3>HTML 构建失败</h3>
<p><strong>错误:</strong></p>
<pre style="background: {tokens['pre_bg']}; color: {tokens['body_text']}; padding: 10px; border-radius: 4px; overflow-x: auto;">{html_module.escape(str(error))}</pre>
</body></html>'''


def _resolve_render_mode_name() -> str:
    """Return the current render mode display name (Typst / LaTeX / MathJax)."""
    try:
        from backend.latex_renderer import _latex_settings
        if _latex_settings:
            mode = _latex_settings.get_render_mode()
            if mode == "typst":
                return "Typst"
            if mode in ("latex_pdflatex", "latex_xelatex"):
                return "LaTeX SVG"
    except Exception:
        pass
    return "MathJax"


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
            print(f"[RenderBlock] Processing block: type={content_type}, label_len={len(label)}, content_len={len(content)}")

        type_name, type_class = {
            "mathcraft": ("公式", ""),
            "mathcraft_text": ("文字", "text"),
            "mathcraft_mixed": ("混合", "mixed"),
        }.get(content_type, ("内容", ""))

        # When the content is a pure formula (wrapped in $$...$$), always
        # use the formula renderer regardless of the content-type tag,
        # so that Typst SVG rendering works for all formula content.
        stripped = content.strip()
        is_pure_formula = stripped.startswith("$$") and stripped.endswith("$$")
        # Content typed as mathcraft_mixed but with NO $ delimiters is
        # a bare formula (e.g. Typst output or raw LaTeX).  Route through
        # the formula renderer so SVG / MathJax can render it.
        # Only treat PROPERLY PAIRED $...$ or $$...$$ as MathJax delimiters;
        # a stray $ (e.g. in Typst pypandoc output) is not a delimiter.
        has_dollar_delim = bool(re.search(r'\$\$(?:[^$]|\$(?!\$))+\$\$|\$(?:[^$]|\$(?!\$))+\$', stripped))

        if content_type == "mathcraft" or is_pure_formula:
            rendered_content = formula_renderer(content)
        elif content_type == "mathcraft_mixed" and not has_dollar_delim:
            rendered_content = formula_renderer(content)
        elif content_type == "mathcraft_mixed":
            rendered_content = render_mixed_content(content)
        else:
            rendered_content = f'<div class="text-content">{html_module.escape(content)}</div>'

        render_mode_name = _resolve_render_mode_name()
        block_class = f"content-block {type_class}-type" if type_class else "content-block"
        badge_class = f"type-badge {type_class}" if type_class else "type-badge"
        result = f'''<div class="{block_class}">
    <div class="block-label">
        <span>{html_module.escape(label or "")}</span>
        <span class="{badge_class}">{type_name}</span>
        <span class="render-mode-badge">{render_mode_name}</span>
    </div>
    <div class="block-content">{rendered_content}</div>
</div>'''
        if debug:
            print(f"[RenderBlock] Render succeeded, output length: {len(result)}")
        return result
    except Exception as exc:
        print(f"[RenderBlock] Block render failed: {exc}")
        tokens = preview_theme_tokens()
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
        is_svg_mode = render_mode and (render_mode.startswith("latex_") or render_mode == "typst")
        is_typst = render_mode == "typst"
        content_is_typst = not looks_like_latex_math(content)

        # Strip outer $$ / $ delimiters so we never double-wrap.
        inner = content.strip()
        inner = re.sub(r'^\$\$?\s*', '', inner)
        inner = re.sub(r'\s*\$\$?\s*$', '', inner)
        # Safety: remove any stray $ characters that remain after
        # stripping (e.g. pypandoc artifacts).  $ is only a MathJax
        # delimiter and must never appear in Typst formula body text.
        inner = inner.replace('$', '')
        inner = inner.strip()
        # Clean up any escaped parens/slashes/etc left over from older
        # buggy conversions (defense-in-depth: the main pipeline already
        # prevents these, but history may contain pre-fix data).
        if is_typst:
            inner = clean_pandoc_typst_artifacts(inner)
        if not inner:
            inner = content.strip()

        if is_svg_mode:
            if has_cached_svg:
                if cached_svg:
                    safe_svg = namespace_svg_ids(cached_svg, cache_key)
                    return f'<div class="formula-content latex-svg">{safe_svg}</div>'
                # Cached but empty: render failed previously.
                if is_typst:
                    # Typst render failed: show raw code (not MathJax, which can't parse Typst).
                    return f'<div class="typst-raw-content">{html_module.escape(inner)}</div>'
                return f'<div class="formula-content">$${inner}$$</div>'
            # No cache yet: schedule async render.
            schedule_render(content)
            if is_typst:
                # Typst: show raw code as placeholder while SVG renders (MathJax can't parse Typst).
                return f'<div class="typst-raw-content">{html_module.escape(inner)}</div>'
            return f'<div class="formula-content">$${inner}$$</div>'

        # Non-SVG fallback (MathJax).  If the content looks like Typst
        # (no LaTeX commands) it cannot be rendered by MathJax; show raw.
        if content_is_typst:
            return f'<div class="typst-raw-content">{html_module.escape(inner)}</div>'
        return f'<div class="formula-content">$${inner}$$</div>'
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
        print(f"[RenderMixed] Mixed content render failed: {exc}")
        return f'<div style="color: red;">{html_module.escape(f"混合内容渲染失败: {exc}")}</div>'
