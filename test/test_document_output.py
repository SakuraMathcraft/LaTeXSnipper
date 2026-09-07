# coding: utf-8


from exporting.document_output import wrap_document_output


def test_document_output_converts_markdown_to_latex() -> None:
    tex = wrap_document_output("## 1 Intro\n\nText with $x$.", "latex", "document")
    assert "\\documentclass" in tex
    assert "\\section{Intro}" in tex
    assert "Text with $x$." in tex


def test_document_output_preserves_markdown_content() -> None:
    markdown = wrap_document_output("# Title\n\nContent", "markdown", "document")
    assert markdown == "# Title\n\nContent\n"


def test_document_output_keeps_existing_latex_document() -> None:
    raw = "\\documentclass{article}\n\\begin{document}\nHi\n\\end{document}\n"
    assert wrap_document_output(raw, "latex", "document") == raw.strip()
