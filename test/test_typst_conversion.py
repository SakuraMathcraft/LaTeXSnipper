# coding: utf-8
# ruff: noqa: E402

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.mathcraft_document_engine import (
    compose_mathcraft_markdown_document,
    compose_mathcraft_markdown_pages,
    convert_latex_to_typst,
)


def test_convert_latex_to_typst_without_pypandoc():
    """Test that convert_latex_to_typst returns original text when pypandoc is not available."""
    # This test assumes pypandoc is not installed
    latex = r"\int_{0}^{\infty} e^{-x} dx"
    result = convert_latex_to_typst(latex)
    assert result == latex


def test_compose_mathcraft_markdown_document_with_typst_formulas():
    """Test that compose_mathcraft_markdown_document accepts typst_formulas parameter."""
    page_texts = [
        "\n".join([
            "Notice that",
            "$$",
            "x = y + z",
            "$$",
            "and continue.",
        ])
    ]

    # Test with typst_formulas=False (default)
    text_default = compose_mathcraft_markdown_document(page_texts)
    assert "$$\nx = y + z\n$$" in text_default

    # Test with typst_formulas=True
    text_typst = compose_mathcraft_markdown_document(page_texts, typst_formulas=True)
    assert isinstance(text_typst, str)
    assert text_typst  # Should not be empty


def test_compose_mathcraft_markdown_pages_with_typst_formulas():
    """Test that compose_mathcraft_markdown_pages accepts typst_formulas parameter."""
    page_results = [
        {
            "text": "\n".join([
                "Notice that",
                "$$",
                "x = y + z",
                "$$",
                "and continue.",
            ])
        }
    ]

    # Test with typst_formulas=False (default)
    text_default = compose_mathcraft_markdown_pages(page_results)
    assert "$$\nx = y + z\n$$" in text_default

    # Test with typst_formulas=True
    text_typst = compose_mathcraft_markdown_pages(page_results, typst_formulas=True)
    assert isinstance(text_typst, str)
    assert text_typst  # Should not be empty


def test_typst_formulas_parameter_consistency():
    """Test that typst_formulas parameter works consistently across functions."""
    page_texts = ["$$a + b = c$$"]
    page_results = [{"text": "$$a + b = c$$"}]

    # Both functions should produce valid output with typst_formulas=True
    doc_text = compose_mathcraft_markdown_document(page_texts, typst_formulas=True)
    pages_text = compose_mathcraft_markdown_pages(page_results, typst_formulas=True)

    assert isinstance(doc_text, str)
    assert isinstance(pages_text, str)
    assert doc_text.strip()
    assert pages_text.strip()


if __name__ == "__main__":
    test_convert_latex_to_typst_without_pypandoc()
    test_compose_mathcraft_markdown_document_with_typst_formulas()
    test_compose_mathcraft_markdown_pages_with_typst_formulas()
    test_typst_formulas_parameter_consistency()
    print("All tests passed!")