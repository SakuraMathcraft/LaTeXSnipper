import pytest

from preview.content_preview import build_mixed_content_html
from preview.math_preview import build_math_html
from rendering.mathjax_runtime import ASSET_ROOT
from preview.smart_preview import build_smart_preview_html
from preview.content_fragments import render_formula_content, render_mixed_content, unwrap_math_delimiters
from runtime.content_types import content_type_for_external_output, content_type_for_mathcraft


def test_local_and_external_results_share_rendering_semantics():
    assert content_type_for_mathcraft("mathcraft") == "mathcraft"
    assert content_type_for_mathcraft("mathcraft_mixed") == "mathcraft_mixed"
    assert content_type_for_mathcraft("mathcraft_text") == "mathcraft_text"

    assert content_type_for_external_output("latex") == "mathcraft"
    assert content_type_for_external_output("markdown") == "mathcraft_mixed"
    assert content_type_for_external_output("text") == "mathcraft_text"


def test_rendering_semantics_reject_missing_or_unknown_metadata():
    with pytest.raises(ValueError):
        content_type_for_mathcraft("")
    with pytest.raises(ValueError):
        content_type_for_external_output("unknown")


def test_mixed_content_escapes_text_and_preserves_formulas():
    html = build_mixed_content_html("<b>x</b>\n$y=1$\n$$z=2$$")

    assert "&lt;b&gt;x&lt;/b&gt;<br>" in html
    assert "$y=1$" in html
    assert "$$z=2$$" in html


def test_mixed_content_uses_bundled_mathjax_runtime():
    html = build_mixed_content_html("$x$")

    assert "LaTeXSnipperMathJax.load" in html
    assert ASSET_ROOT.resolve().as_uri() in html
    assert '"output": "chtml"' in html
    assert '"scale": 1.2' in html


def test_smart_preview_uses_bundled_mathjax_runtime():
    html = build_smart_preview_html(
        [("$x$", "Formula", "mathcraft")],
    )

    assert ASSET_ROOT.resolve().as_uri() in html
    assert "LaTeXSnipperMathJax.load" in html
    assert "color-scheme:" in html
    assert "::-webkit-scrollbar-thumb" in html


def test_math_preview_can_center_single_formula_in_viewport():
    normal_html = build_math_html("x")
    centered_html = build_math_html("x", center_viewport=True)

    assert 'body class=""' in normal_html
    assert 'body class="viewport-centered"' in centered_html
    assert "body.viewport-centered" in centered_html


def test_formula_record_with_document_content_keeps_headings_outside_math_mode():
    content = '### 试卷片段\n正文 $x<y$\n$$\\begin{cases}x+1<2x-1\\\\x-1>0\\end{cases}$$'
    for page in (build_smart_preview_html([(content, 'Exam', 'mathcraft')]), build_math_html(content)):
        assert '### 试卷片段<br>正文 $x&lt;y$' in page
        assert '$$###' not in page
        assert '$$\\begin{cases}' in page


@pytest.mark.parametrize('content', ['$x$', '$$x$$', r'\(x\)', r'\[x\]', '```latex\nx^2\n```'])
def test_explicit_math_or_fence_does_not_add_nested_delimiters(content):
    normalized = unwrap_math_delimiters(content)
    assert normalized in {'x', 'x^2'}
    assert '$$$' not in render_formula_content(content)


def test_math_fragments_escape_inequalities_and_protect_static_svg_diagrams():
    content = r'''# 试题
<svg width="100" height="80"><path d="M0 0 L80 80" stroke="#123456"/><script>bad()</script></svg>
\[x<y\]，\(x>0\)'''
    rendered = render_mixed_content(content)
    assert '<svg ' in rendered and '<path ' in rendered
    assert 'stroke="#123456"' in rendered
    assert '<script>' not in rendered
    assert r'\[x&lt;y\]' in rendered and r'\(x&gt;0\)' in rendered


def test_multiple_math_regions_are_not_unwrapped_as_one_formula():
    content = '$x$，$y$'
    assert unwrap_math_delimiters(content) == content
    assert render_formula_content(content).count('$') == 4
