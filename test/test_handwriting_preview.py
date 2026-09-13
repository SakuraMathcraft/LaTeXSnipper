from __future__ import annotations


def test_handwriting_latex_preview_keeps_multiline_environment_together() -> None:
    from handwriting.latex_preview import (
        build_handwriting_preview_html,
        normalize_latex_preview_source,
    )

    latex = "\\begin{aligned}\nM_{C lie H Craft}\\\\\n\\int_0^1 x^2 dx\n\\end{aligned}"

    assert normalize_latex_preview_source(latex) == latex

    html = build_handwriting_preview_html(latex, "latex")

    assert "\\begin{aligned}" in html
    assert "\\end{aligned}" in html
    assert '<div class="math-block">' not in html


def test_handwriting_markdown_preview_preserves_text_and_math() -> None:
    from handwriting.latex_preview import build_handwriting_preview_html
    from preview.math_preview import MATHJAX_CDN_URL_BACKUP

    html = build_handwriting_preview_html(
        "京文子\nMathCraft\n$$\\int_0^1 x^2 dx$$", "markdown"
    )

    assert "京文子" in html
    assert "MathCraft" in html
    assert "$$\\int_0^1 x^2 dx$$" in html
    assert "startup.js" in html
    assert MATHJAX_CDN_URL_BACKUP.rsplit("/", 1)[0] in html
    assert "LaTeXSnipperMathJax.load" in html
    assert "::-webkit-scrollbar-thumb" in html
