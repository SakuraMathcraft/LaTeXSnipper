from __future__ import annotations

import fitz
from PIL import Image

from mathcraft_ocr.layout import annotate_blocks
from mathcraft_ocr.pdf_text import has_native_columns, native_text_blocks
from mathcraft_ocr.results import MathCraftBlock
from mathcraft_ocr.serialization import block_to_json
from recognition.jobs import RecognitionJobCoordinator
from recognition.pdf_text import visible_pdf_text
from recognition.postprocessing.mathcraft_document import (
    compose_mathcraft_markdown_pages,
)
from recognition.workers import PdfPredictWorker

_TEXT_FLAGS = fitz.TEXTFLAGS_RAWDICT & ~(
    fitz.TEXT_PRESERVE_IMAGES | fitz.TEXT_CID_FOR_UNKNOWN_UNICODE
)


def test_native_article_preserves_author_outline_and_column_order():
    with fitz.open() as pdf:
        page = pdf.new_page(width=600, height=800)

        def centered(text, y, size):
            width = fitz.get_text_length(text, fontsize=size)
            page.insert_text(((600 - width) / 2, y), text, fontsize=size)

        centered("A Study of Discrete Systems", 74, 24)
        centered("Ada Lovelace and Sofia Kovalevskaya", 99, 11)
        page.insert_text((45, 155), "I. Introduction", fontsize=12)
        page.insert_text((320, 155), "II. Main Results", fontsize=12)
        page.insert_text((320, 178), "A. Stability", fontsize=11)
        for index in range(4):
            page.insert_text(
                (45, 180 + index * 18), "The left column develops the argument."
            )
            page.insert_text(
                (320, 198 + index * 18), "The right column contains the results."
            )
        page.insert_text((320, 282), "Theorem 1.", fontname="hebo")
        page.insert_text((379, 282), "Every point is fixed.")
        lines = visible_pdf_text(
            page,
            text_flags=_TEXT_FLAGS,
            outline=[(1, "Introduction"), (1, "Main Results"), (2, "Stability")],
        )
    assert lines is not None
    assert has_native_columns(lines)
    blocks = native_text_blocks(lines, [], (600, 800))
    assert blocks is not None
    result = compose_mathcraft_markdown_pages(
        [
            {
                "image_size": [600, 800],
                "blocks": [
                    block_to_json(block)
                    for block in annotate_blocks(
                        blocks, image_size=(600, 800), native_two_columns=True
                    )
                ],
            }
        ]
    )
    assert result.startswith(
        "# A Study of Discrete Systems\n\n*Ada Lovelace and Sofia Kovalevskaya*"
    )
    assert result.index("## I. Introduction") < result.index("The left column")
    assert result.rindex("The left column") < result.index("## II. Main Results")
    assert "### A. Stability" in result
    assert "**Theorem 1.** Every point is fixed." in result


def test_native_text_rejects_invisible_ocr_layer():
    with fitz.open() as pdf:
        page = pdf.new_page()
        for row in range(5):
            page.insert_text(
                (50, 100 + row * 20),
                "This invisible OCR layer does not match the page.",
                render_mode=3,
            )
        assert visible_pdf_text(page, text_flags=_TEXT_FLAGS, outline=[]) is None


def test_native_single_column_article_with_same_size_title_and_body():
    with fitz.open() as pdf:
        page = pdf.new_page(width=600, height=800)
        for text, y, font, size in (
            ("A SINGLE COLUMN ARTICLE", 120, "hebo", 11),
            ("Sofia Kovalevskaya", 144, "helv", 9),
        ):
            width = fitz.get_text_length(text, fontname=font, fontsize=size)
            page.insert_text(((600 - width) / 2, y), text, fontname=font, fontsize=size)
        for row in range(5):
            page.insert_text(
                (50, 180 + 20 * row),
                "The argument develops across the full width of the page, including inline formulas.",
            )
        for row in range(3):
            y = 190 + 20 * row
            page.insert_text((80, y), "A group of fragments")
            page.insert_text((330, y), "Another group of fragments")
        page.insert_text((50, 750), "12 |", fontsize=15)
        lines = visible_pdf_text(page, text_flags=_TEXT_FLAGS, outline=[])

    assert lines is not None
    assert not has_native_columns(lines)
    classified = [
        (line["heading_level"], line["role"], "".join(g[0] for g in line["glyphs"]))
        for line in lines
    ]
    assert (1, "", "A SINGLE COLUMN ARTICLE") in classified
    assert (None, "author", "Sofia Kovalevskaya") in classified
    assert all(text != "12 |" for _, _, text in classified)


def test_native_outline_distinguishes_equal_titles_with_different_numbers():
    with fitz.open() as pdf:
        page = pdf.new_page(width=600, height=800)
        page.insert_text((440, 48), "2.3 Regular Values")
        page.insert_text((60, 95), "2.3 Regular Values", fontname="hebo", fontsize=14)
        page.insert_text(
            (60, 135), "2.3.2 Regular Values", fontname="hebo", fontsize=12
        )
        for row in range(5):
            page.insert_text(
                (60, 170 + row * 20),
                "The regular values of a smooth function are dense.",
            )
        lines = visible_pdf_text(
            page,
            text_flags=_TEXT_FLAGS,
            outline=[(2, "2.3 Regular Values"), (3, "2.3.2 Regular Values")],
        )

    assert lines is not None
    headings = [
        (line["heading_level"], "".join(g[0] for g in line["glyphs"]))
        for line in lines
        if line["heading_level"]
    ]
    assert headings == [(3, "2.3 Regular Values"), (4, "2.3.2 Regular Values")]


def test_native_text_replaces_formula_glyphs_and_keeps_adjacent_prose():
    line = {
        "glyphs": [
            ("Let ", 0.10, 0.20, 0.15, 0.22, False),
            ("\ufffd", 0.16, 0.20, 0.18, 0.22, False),
            (" be fixed.", 0.19, 0.20, 0.30, 0.22, False),
        ],
        "paragraph": 2,
        "heading_level": None,
        "role": "",
    }
    formula = MathCraftBlock(
        "embedding", ((155, 199), (185, 199), (185, 225), (155, 225)), "x", 0.9
    )
    assert native_text_blocks([line], [], (1000, 1000)) is None
    blocks = native_text_blocks([line], [formula], (1000, 1000))
    assert blocks is not None
    assert [block.text for block in blocks] == ["Let", "be fixed."]


def test_pdf_job_passes_the_native_layer_and_returns_the_structured_result():
    class Predictor:
        def predict_result(self, image, *, model_name, pdf_text_lines):
            assert model_name == "mathcraft_mixed"
            assert pdf_text_lines == lines
            return {
                "text": "Title",
                "image_size": list(image.size),
                "blocks": [{"text": "Title", "heading_level": 1}],
            }

    lines = [
        {
            "glyphs": [("T", 0.1, 0.1, 0.2, 0.2, True)],
            "paragraph": 0,
            "heading_level": 1,
            "role": "",
        }
    ]
    coordinator = RecognitionJobCoordinator(Predictor())
    try:
        worker = PdfPredictWorker(coordinator, "", [0], "mathcraft_mixed", "markdown")
        page = worker._predict_page(Image.new("RGB", (500, 600)), lines)
        assert page["blocks"] == [{"text": "Title", "heading_level": 1}]
        assert page["image_size"] == [500, 600]
    finally:
        coordinator.stop()
