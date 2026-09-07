from __future__ import annotations


def test_wrap_tex_document_normalizes_external_article_document() -> None:
    from preview.document.tex_utils import wrap_tex_document

    wrapped = wrap_tex_document(
        "\\documentclass{article}\n"
        "\\usepackage{amsmath}\n"
        "\\begin{document}\n"
        "MathCraft\n"
        "$$\\int_0^1 \\Gamma(x) dx$$\n"
        "\\end{document}"
    )

    assert "\\documentclass[UTF8]{ctexart}" in wrapped
    assert "\\documentclass{article}" not in wrapped
    assert "\\usepackage{amsmath,amssymb,amsthm,mathtools,bm}" in wrapped
    assert "\\usepackage{geometry}" in wrapped
    assert "\\geometry{a4paper,margin=2.2cm}" in wrapped
    assert "\\[\n\\int_0^1 \\Gamma(x) dx\n\\]" in wrapped
    assert wrapped.count("\\begin{document}") == 1
    assert wrapped.count("\\end{document}") == 1


def test_wrap_tex_document_preserves_plain_text_lines_as_paragraphs() -> None:
    from preview.document.tex_utils import wrap_tex_document

    wrapped = wrap_tex_document("Hello\nMathCraft\n$$\\int_0^1 \\Gamma(x) dx$$")

    body = wrapped.split("\\begin{document}", 1)[1].split("\\end{document}", 1)[0]
    assert "Hello\n\nMathCraft" in body
    assert "\\[\n\\int_0^1 \\Gamma(x) dx\n\\]" in body


def test_wrap_tex_document_completes_external_partial_document() -> None:
    from preview.document.tex_utils import wrap_tex_document

    wrapped = wrap_tex_document(
        "\\documentclass{article}\n"
        "\\usepackage{amsmath}\n"
        "\\begin{document}\n"
        "\\int_0^1 x^2 dx"
    )

    assert wrapped.startswith("\\documentclass[UTF8]{ctexart}")
    assert "\\end{document}" in wrapped


def test_merge_layout_with_recognized_draft_restores_dropped_text() -> None:
    from preview.document.tex_utils import merge_layout_with_recognized_draft

    merged = merge_layout_with_recognized_draft(
        "\\documentclass[UTF8]{ctexart}\n"
        "\\begin{document}\n"
        "Math\n"
        "\\[\n"
        "\\int_0^1 \\Gamma(x) dx\n"
        "\\]\n"
        "\\end{document}",
        "MathCraft\n$$\\int_0^1 \\Gamma(x) dx$$",
    )

    body = merged.split("\\begin{document}", 1)[1].split("\\end{document}", 1)[0]
    assert "MathCraft" in body
    assert "\nMath\n" not in body
    assert "\\int_0^1 \\Gamma(x) dx" in body


def test_merge_layout_with_recognized_draft_keeps_existing_text_once() -> None:
    from preview.document.tex_utils import merge_layout_with_recognized_draft

    merged = merge_layout_with_recognized_draft(
        "\\documentclass[UTF8]{ctexart}\n"
        "\\begin{document}\n"
        "MathCraft\n"
        "\\[\n"
        "x^2\n"
        "\\]\n"
        "\\end{document}",
        "MathCraft\n$$x^2$$",
    )

    assert merged.count("MathCraft") == 1


def test_merge_layout_with_recognized_draft_preserves_multiple_text_lines() -> None:
    from preview.document.tex_utils import merge_layout_with_recognized_draft

    merged = merge_layout_with_recognized_draft(
        "\\documentclass[UTF8]{ctexart}\n"
        "\\begin{document}\n"
        "\\[\n"
        "\\int_0^1 \\Gamma(x) dx\n"
        "\\]\n"
        "\\end{document}",
        "Hello\nMathCraft\n$$\\int_0^1 \\Gamma(x) dx$$",
    )

    body = merged.split("\\begin{document}", 1)[1].split("\\end{document}", 1)[0]
    assert "Hello\n\nMathCraft" in body
