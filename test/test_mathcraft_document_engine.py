# coding: utf-8
# ruff: noqa: E402

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.mathcraft_document_engine import compose_mathcraft_markdown_document, compose_mathcraft_markdown_pages


def test_document_engine_promotes_title_and_sections() -> None:
    text = compose_mathcraft_markdown_document(
        [
            "\n".join(
                [
                    "The Brouwer Fixed Point Theorem",
                    "A. Ginory",
                    "1 Introduction",
                    "We explore some proofs of the famous fixed point theorem.",
                ]
            )
        ]
    )
    assert "# The Brouwer Fixed Point Theorem\n\nA. Ginory" in text
    assert "## 1 Introduction" in text


def test_document_engine_preserves_display_math() -> None:
    text = compose_mathcraft_markdown_document(
        [
            "\n".join(
                [
                    "Notice that",
                    "$$",
                    "x = y + z",
                    "$$",
                    "and continue.",
                ]
            )
        ]
    )
    assert "$$\nx = y + z\n$$" in text


def test_document_engine_can_render_typst_formulas() -> None:
    text = compose_mathcraft_markdown_document(
        [
            "\n".join(
                [
                    "Notice that",
                    "$$",
                    "x = y + z",
                    "$$",
                    "and continue.",
                ]
            )
        ],
        typst_formulas=True,
    )
    assert isinstance(text, str)
    assert text


def test_document_engine_merges_cross_page_continuation() -> None:
    text = compose_mathcraft_markdown_document(
        [
            "we can find a polynomial",
            "map $\\alpha : D ^ { n } \\to \\mathbb { R } ^ { n }$ such that it works.",
        ]
    )
    assert (
        "we can find a polynomial map $\\alpha : D ^ { n } \\to \\mathbb { R } ^ { n }$ such that it works."
        in text
    )
    assert "<!-- Page 2 -->" not in text


def test_document_engine_keeps_page_comment_when_not_continuation() -> None:
    text = compose_mathcraft_markdown_document(
        [
            "This paragraph ends.",
            "2 Differential Geometry\nA new section starts.",
        ]
    )
    assert "<!-- Page 2 -->" in text
    assert "## 2 Differential Geometry" in text


def test_document_engine_formats_theorem_leads_and_hyphenation() -> None:
    text = compose_mathcraft_markdown_document(
        [
            "\n".join(
                [
                    "The classifi-",
                    "cation is useful.",
                    "Theorem 2.1 (Stone-Weierstrass Approximation Theorem). Let $X$ be compact.",
                ]
            )
        ]
    )
    assert "The classification is useful." in text
    assert "**Theorem 2.1 (Stone-Weierstrass Approximation Theorem).** Let $X$ be compact." in text


def test_document_engine_repairs_split_fi_ligature_text() -> None:
    text = compose_mathcraft_markdown_document(
        ["The classifi cation of fi nitely many components is useful."]
    )
    assert "classification of finitely many components" in text


def test_document_engine_splits_after_completed_proof_marker() -> None:
    text = compose_mathcraft_markdown_document(
        [
            "\n".join(
                [
                    "Proof. See [Lee13]. □",
                    "The specialized result that follows implies another corollary.",
                ]
            )
        ]
    )
    assert "**Proof.** See [Lee13]. □\n\nThe specialized result" in text


def test_document_engine_keeps_front_matter_blocks_separate() -> None:
    text = compose_mathcraft_markdown_document(
        [
            "Abstract Algebra\nTheory and Applications",
            "\n".join(
                [
                    "Abstract Algebra",
                    "Theory and Applications",
                    "Thomas W. Judson",
                    "Stephen F. Austin State University",
                    "July 28, 2022",
                ]
            ),
            "\n".join(
                [
                    "Acknowledgements",
                    "I would like to acknowledge the following reviewers.",
                    "• David Anderson, University of Tennessee, Knoxville",
                    "iv",
                ]
            ),
        ]
    )
    assert text.startswith("# Abstract Algebra Theory and Applications")
    assert "Thomas W. Judson\n\nStephen F. Austin State University" in text
    assert "## Acknowledgements" in text
    assert "- David Anderson, University of Tennessee, Knoxville" in text
    assert "\niv\n" not in text


def test_document_engine_keeps_chapter_chart_lines_out_of_body_paragraphs() -> None:
    text = compose_mathcraft_markdown_document(
        [
            "\n".join(
                [
                    "vi",
                    "Chapters 1–6",
                    "Chapter 8 Chapter 9 Chapter 7",
                    "Chapter 10",
                    "Though there are no specific prerequisites for a course.",
                ]
            )
        ]
    )
    assert "- Chapters 1–6" in text
    assert "- Chapter 8 Chapter 9 Chapter 7" in text
    assert "- Chapter 10" in text
    assert "Chapter 7 Though there" not in text
    assert "Chapter 10 Though there" not in text
    assert "\nvi\n" not in text


def test_document_engine_combines_real_chapter_label_with_title() -> None:
    text = compose_mathcraft_markdown_document(
        [
            "\n".join(
                [
                    "Chapter 1",
                    "Special Limits",
                    "The last thing one knows when writing a book is what to put",
                    "first.",
                ]
            )
        ]
    )
    assert "## Chapter 1 Special Limits" in text
    assert "- Chapter 1" not in text


def test_document_engine_removes_running_headers() -> None:
    text = compose_mathcraft_markdown_document(
        [
            "\n".join(
                [
                    "CHAPTER 3. GROUPS 34",
                    "The law of composition is associative.",
                    "CONTENTS ix",
                    "2 1 Special Limits",
                    "1 Introduction",
                    "Body.",
                ]
            )
        ]
    )
    assert "CHAPTER 3. GROUPS 34" not in text
    assert "CONTENTS ix" not in text
    assert "2 1 Special Limits" not in text
    assert "The law of composition is associative." in text


def test_document_engine_detects_chinese_section_headings() -> None:
    text = compose_mathcraft_markdown_document(
        [
            "\n".join(
                [
                    "第1章前言",
                    "1.1学员看",
                    "本书是讲义。",
                ]
            )
        ]
    )
    assert "## 第1章 前言" in text
    assert "### 1.1 学员看" in text


def test_document_engine_cleans_common_mathcraft_ocr_artifacts() -> None:
    text = compose_mathcraft_markdown_document(
        [
            "\n".join(
                [
                    "$\\neg$",
                    "Preliminaries",
                    "1.1 A Short Note on Proofs",
                    "·• All cats are black.",
                    "・ $2 + 3 = 5$",
                    "Example 1. 1 Let $A$ be a set.",
                    "PRooF. This is clear.",
                    "$$ []",
                    "x = y",
                    "[]$$",
                ]
            )
        ]
    )
    assert "$\\neg$" not in text
    assert "# Preliminaries" in text
    assert "- All cats are black." in text
    assert "- $2 + 3 = 5$" in text
    assert "**Example 1.1.** Let $A$ be a set." in text
    assert "**Proof.** This is clear." in text
    assert "$$\nx = y\n$$" in text
    assert "[]" not in text


def test_document_engine_repairs_bracketed_display_math_marker() -> None:
    text = compose_mathcraft_markdown_document(
        [
            "\n".join(
                [
                    "Notice that",
                    "[$$",
                    "x = y",
                    "$$",
                ]
            )
        ]
    )
    assert "$$\nx = y\n$$" in text
    assert "[$$" not in text


def test_document_engine_splits_text_before_display_math_marker() -> None:
    text = compose_mathcraft_markdown_document(
        [
            "\n".join(
                [
                    "1.11. Find []$$",
                    "x = y",
                    "$$",
                ]
            )
        ]
    )
    assert "1.11. Find\n\n$$\nx = y\n$$" in text
    assert "Find $$" not in text


def test_document_engine_renders_contents_entries_as_list_items() -> None:
    text = compose_mathcraft_markdown_document(
        [
            "\n".join(
                [
                    "Contents",
                    "1 Special Limits 1",
                    "1.1 Miscellaneous Limits 1",
                    "2 Fractional Part Integrals 99",
                ]
            )
        ]
    )
    assert "## Contents" in text
    assert "- 1 Special Limits 1" in text
    assert "- 1.1 Miscellaneous Limits 1" in text
    assert "## 1 Special Limits 1" not in text
    assert "### 1.1 Miscellaneous Limits 1" not in text


def test_document_engine_does_not_promote_split_exercise_numbers() -> None:
    text = compose_mathcraft_markdown_document(
        [
            "\n".join(
                [
                    "1.1 Miscellaneous Limits",
                    "1.1 1. Find $$",
                    "x = y",
                    "$$",
                ]
            )
        ]
    )
    assert "### 1.1 Miscellaneous Limits" in text
    assert "### 1.1 1. Find" not in text
    assert "1.1 1. Find" in text


def test_document_engine_uses_structured_blocks_for_pdf_pages() -> None:
    text = compose_mathcraft_markdown_pages(
        [
            {
                "image_size": [1000, 1400],
                "blocks": [
                    {
                        "kind": "text",
                        "box": [[100, 80], [180, 80], [180, 105], [100, 105]],
                        "text": "1",
                        "score": 0.99,
                    },
                    {
                        "kind": "text",
                        "box": [[250, 82], [620, 82], [620, 108], [250, 108]],
                        "text": "CHAPTER 1. PRELIMINARIES",
                        "score": 0.99,
                    },
                    {
                        "kind": "text",
                        "box": [[100, 160], [520, 160], [520, 200], [100, 200]],
                        "text": "1 Introduction",
                        "score": 0.99,
                    },
                    {
                        "kind": "text",
                        "box": [[100, 240], [340, 240], [340, 270], [100, 270]],
                        "text": "Let",
                        "score": 0.99,
                    },
                    {
                        "kind": "embedding",
                        "box": [[355, 238], [430, 238], [430, 272], [355, 272]],
                        "text": "x = y",
                        "score": 0.99,
                    },
                    {
                        "kind": "text",
                        "box": [[445, 240], [620, 240], [620, 270], [445, 270]],
                        "text": "hold.",
                        "score": 0.99,
                    },
                    {
                        "kind": "isolated",
                        "box": [[220, 340], [780, 340], [780, 420], [220, 420]],
                        "text": "a = b + c",
                        "score": 0.99,
                    },
                ],
            }
        ]
    )
    assert "\n1\n" not in f"\n{text}\n"
    assert "CHAPTER 1. PRELIMINARIES" not in text
    assert "## 1 Introduction" in text
    assert "Let $x = y$ hold." in text
    assert "$$\na = b + c\n$$" in text


def test_document_engine_consumes_structured_roles_and_paragraphs() -> None:
    text = compose_mathcraft_markdown_pages(
        [
            {
                "image_size": [1000, 1200],
                "blocks": [
                    {
                        "kind": "text",
                        "role": "header",
                        "box": [[300, 30], [700, 30], [700, 55], [300, 55]],
                        "text": "CHAPTER 2. METHODS 12",
                        "score": 0.99,
                    },
                    {
                        "kind": "text",
                        "role": "heading",
                        "paragraph_id": 1,
                        "box": [[100, 120], [420, 120], [420, 150], [100, 150]],
                        "text": "2 Methods",
                        "score": 0.99,
                    },
                    {
                        "kind": "text",
                        "role": "paragraph",
                        "paragraph_id": 2,
                        "box": [[100, 220], [480, 220], [480, 250], [100, 250]],
                        "text": "First line continues",
                        "score": 0.99,
                    },
                    {
                        "kind": "text",
                        "role": "paragraph",
                        "paragraph_id": 2,
                        "box": [[100, 255], [380, 255], [380, 285], [100, 285]],
                        "text": "here.",
                        "score": 0.99,
                    },
                    {
                        "kind": "text",
                        "role": "paragraph",
                        "paragraph_id": 3,
                        "box": [[100, 340], [430, 340], [430, 370], [100, 370]],
                        "text": "Another paragraph starts.",
                        "score": 0.99,
                    },
                    {
                        "kind": "text",
                        "role": "list",
                        "paragraph_id": 4,
                        "box": [[100, 410], [340, 410], [340, 440], [100, 440]],
                        "text": "- one item",
                        "score": 0.99,
                    },
                    {
                        "kind": "text",
                        "role": "page_number",
                        "box": [[490, 1140], [510, 1140], [510, 1160], [490, 1160]],
                        "text": "12",
                        "score": 0.99,
                    },
                ],
            }
        ]
    )
    assert "CHAPTER 2. METHODS" not in text
    assert "\n12\n" not in f"\n{text}\n"
    assert "## 2 Methods" in text
    assert "First line continues here. Another paragraph starts." in text
    assert "- one item" in text


def test_document_engine_prefers_runtime_line_order_and_display_flag() -> None:
    text = compose_mathcraft_markdown_pages(
        [
            {
                "image_size": [1000, 1200],
                "blocks": [
                    {
                        "kind": "text",
                        "box": [[620, 100], [760, 100], [760, 120], [620, 120]],
                        "text": "right one",
                        "score": 0.99,
                        "line_id": 2,
                        "reading_order": 2,
                        "page_index": 1,
                        "image_size": [1000, 1200],
                    },
                    {
                        "kind": "isolated",
                        "box": [[100, 260], [420, 260], [420, 320], [100, 320]],
                        "text": "x = y",
                        "score": 0.99,
                        "line_id": 1,
                        "reading_order": 1,
                        "is_display": True,
                        "page_index": 1,
                        "image_size": [1000, 1200],
                    },
                    {
                        "kind": "text",
                        "box": [[100, 100], [240, 100], [240, 120], [100, 120]],
                        "text": "left one",
                        "score": 0.99,
                        "line_id": 0,
                        "reading_order": 0,
                        "page_index": 1,
                        "image_size": [1000, 1200],
                    },
                ],
            }
        ]
    )
    assert text.index("left one") < text.index("$$\nx = y\n$$") < text.index("right one")


def test_document_engine_keeps_centered_formula_between_left_column_lines() -> None:
    text = compose_mathcraft_markdown_pages(
        [
            {
                "image_size": [1000, 1200],
                "blocks": [
                    {
                        "kind": "text",
                        "box": [[100, 100], [240, 100], [240, 120], [100, 120]],
                        "text": "left one",
                        "score": 0.99,
                    },
                    {
                        "kind": "text",
                        "box": [[620, 100], [760, 100], [760, 120], [620, 120]],
                        "text": "right one",
                        "score": 0.99,
                    },
                    {
                        "kind": "isolated",
                        "box": [[420, 150], [580, 150], [580, 190], [420, 190]],
                        "text": "x = y",
                        "score": 0.99,
                    },
                    {
                        "kind": "text",
                        "box": [[100, 220], [240, 220], [240, 240], [100, 240]],
                        "text": "left two",
                        "score": 0.99,
                    },
                ],
            }
        ]
    )
    assert text.index("left one") < text.index("$$\nx = y\n$$") < text.index("left two")
    assert text.index("left two") < text.index("right one")


def test_document_engine_keeps_formula_anchors_out_of_paragraph_merge() -> None:
    text = compose_mathcraft_markdown_pages(
        [
            {
                "image_size": [1000, 1200],
                "blocks": [
                    {
                        "kind": "text",
                        "role": "formula_anchor",
                        "box": [[100, 120], [170, 120], [170, 145], [100, 145]],
                        "text": "where",
                        "score": 0.99,
                        "line_id": 0,
                        "reading_order": 0,
                        "column": 0,
                    },
                    {
                        "kind": "isolated",
                        "role": "formula",
                        "is_display": True,
                        "box": [[180, 150], [520, 150], [520, 300], [180, 300]],
                        "text": r"\begin{aligned} x &= y \end{aligned}",
                        "score": 0.99,
                        "line_id": 1,
                        "reading_order": 1,
                        "column": 0,
                    },
                    {
                        "kind": "text",
                        "role": "formula_label",
                        "box": [[540, 190], [585, 190], [585, 215], [540, 215]],
                        "text": "(16)",
                        "score": 0.99,
                        "line_id": 2,
                        "reading_order": 2,
                        "column": 0,
                    },
                ],
            }
        ]
    )
    assert "where\n\n$$" in text
    assert "$$\n\\begin{aligned} x &= y \\end{aligned}\n$$" in text
    assert "$$ where" not in text
    assert "$$$$" not in text


def main() -> None:
    tests = [
        test_document_engine_promotes_title_and_sections,
        test_document_engine_preserves_display_math,
        test_document_engine_merges_cross_page_continuation,
        test_document_engine_keeps_page_comment_when_not_continuation,
        test_document_engine_formats_theorem_leads_and_hyphenation,
        test_document_engine_repairs_split_fi_ligature_text,
        test_document_engine_splits_after_completed_proof_marker,
        test_document_engine_keeps_front_matter_blocks_separate,
        test_document_engine_keeps_chapter_chart_lines_out_of_body_paragraphs,
        test_document_engine_combines_real_chapter_label_with_title,
        test_document_engine_removes_running_headers,
        test_document_engine_detects_chinese_section_headings,
        test_document_engine_cleans_common_mathcraft_ocr_artifacts,
        test_document_engine_repairs_bracketed_display_math_marker,
        test_document_engine_splits_text_before_display_math_marker,
        test_document_engine_renders_contents_entries_as_list_items,
        test_document_engine_does_not_promote_split_exercise_numbers,
        test_document_engine_uses_structured_blocks_for_pdf_pages,
        test_document_engine_consumes_structured_roles_and_paragraphs,
        test_document_engine_prefers_runtime_line_order_and_display_flag,
        test_document_engine_keeps_centered_formula_between_left_column_lines,
        test_document_engine_keeps_formula_anchors_out_of_paragraph_merge,
    ]
    for test in tests:
        test()
    print(f"{len(tests)} tests OK")


if __name__ == "__main__":
    main()
