# coding: utf-8
# ruff: noqa: E402

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.mathcraft_tex_exporter import markdown_to_latex_document
from core.pdf_output_contract import wrap_document_output


def test_tex_exporter_converts_core_markdown_blocks() -> None:
    markdown = "\n".join(
        [
            "# Sample Document",
            "",
            "## 1 Introduction",
            "",
            "Let $X \\subseteq \\mathbb { R }$ and **Proof.** This uses A_B & C.",
            "",
            "- First item with $x_1$",
            "- Second item",
            "",
            "$$",
            "x = y + z",
            "$$",
            "",
            "<!-- Page 2 -->",
        ]
    )
    tex = markdown_to_latex_document(markdown)
    assert tex.startswith("\\documentclass")
    assert "\\title{Sample Document}" in tex
    assert "\\section{Introduction}" in tex
    assert "\\section{1 Introduction}" not in tex
    assert "$X \\subseteq \\mathbb { R }$" in tex
    assert "\\textbf{Proof.}" in tex
    assert "A\\_B \\& C" in tex
    assert "\\begin{itemize}" in tex
    assert "\\item First item with $x_1$" in tex
    assert "\\[\nx = y + z\n\\]" in tex
    assert "% Page 2" in tex
    assert "$$" not in tex
    assert "## 1 Introduction" not in tex


def test_pdf_output_contract_converts_markdown_to_latex() -> None:
    tex = wrap_document_output("## 1 Intro\n\nText with $x$.", "latex", "document")
    assert "\\documentclass" in tex
    assert "\\section{Intro}" in tex
    assert "Text with $x$." in tex


def test_tex_exporter_strips_auto_numbered_heading_prefixes() -> None:
    tex = markdown_to_latex_document(
        "\n".join(
            [
                "## Chapter 1 Special Limits",
                "### 1.1 Miscellaneous Limits",
                "#### 9.2.1 二重极限",
                "## 第1章 前言",
            ]
        )
    )
    assert "\\section{Special Limits}" in tex
    assert "\\subsection{Miscellaneous Limits}" in tex
    assert "\\subsubsection{二重极限}" in tex
    assert "\\section{前言}" in tex
    assert "Chapter 1 Special Limits" not in tex


def test_tex_exporter_repairs_ocr_truncated_display_math() -> None:
    tex = markdown_to_latex_document(
        "\n".join(
            [
                "$$",
                r"\begin{aligned} { x } & { = \frac { 1 } { 2 } \\ { y } & { = -",
                "$$",
                "$$",
                r"\left( \begin{matrix} { x } \\ \end{matrix} + \frac { 1 } \ ",
                "$$",
            ]
        )
    )
    assert "\\end{aligned}" in tex
    assert "\\left" not in tex
    assert "\\right" not in tex
    assert "\\frac { 1 } { 2 }" in tex
    assert "\\frac { 1 } {}" in tex
    assert "\\end{matrix} \\\n\\]" not in tex


def test_pdf_output_contract_keeps_existing_latex_document() -> None:
    raw = "\\documentclass{article}\n\\begin{document}\nHi\n\\end{document}\n"
    assert wrap_document_output(raw, "latex", "document") == raw.strip()


def test_existing_pdf_markdown_samples_convert_to_latex() -> None:
    sample_root = ROOT / "test_pdf" / "outputs"
    sample_paths = sorted(sample_root.glob("**/document_engine.md"))
    assert sample_paths
    for path in sample_paths:
        tex = markdown_to_latex_document(path.read_text(encoding="utf-8"))
        assert "\\documentclass" in tex, path
        assert "\\begin{document}" in tex, path
        assert "\\end{document}" in tex, path
        assert "<!--" not in tex, path
        assert "$$" not in tex, path


def main() -> None:
    tests = [
        test_tex_exporter_converts_core_markdown_blocks,
        test_pdf_output_contract_converts_markdown_to_latex,
        test_tex_exporter_strips_auto_numbered_heading_prefixes,
        test_tex_exporter_repairs_ocr_truncated_display_math,
        test_pdf_output_contract_keeps_existing_latex_document,
        test_existing_pdf_markdown_samples_convert_to_latex,
    ]
    for test in tests:
        test()
    print(f"{len(tests)} tests OK")


if __name__ == "__main__":
    main()
