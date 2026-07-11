from __future__ import annotations

import os
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

from exporting.document_assets import prepare_pandoc_document, supports_document_assets


SVG_ONE = """<svg width="120" height="80" viewBox="0 0 120 80" xmlns="http://www.w3.org/2000/svg">
<rect x="5" y="5" width="110" height="70" fill="none" stroke="black"/>
<text x="20" y="45">A</text>
</svg>"""

SVG_TWO = """<svg width="90" height="60" xmlns="http://www.w3.org/2000/svg">
<circle cx="45" cy="30" r="24" fill="#88c"/>
</svg>"""


@pytest.fixture(scope="module", autouse=True)
def _qt_application():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    yield app


def test_pandoc_asset_formats_are_explicit() -> None:
    assert supports_document_assets("pandoc_docx")
    assert supports_document_assets("pandoc_epub")
    assert supports_document_assets("pandoc_odt")
    assert supports_document_assets("pandoc_pptx")
    assert supports_document_assets("pandoc_pdf")
    assert not supports_document_assets("pandoc_html_standalone")


def test_complete_svg_blocks_are_saved_and_replaced_in_order(tmp_path: Path) -> None:
    source = f"Heading\n\n{SVG_ONE}\n\nMiddle\n\n{SVG_TWO}\n\nEnd"

    prepared = prepare_pandoc_document(source, tmp_path / "report.docx")

    assert prepared.skipped_svg_count == 0
    assert prepared.asset_dir is not None
    assert prepared.asset_dir.name.startswith("report_assets_")
    assert len(prepared.assets) == 2
    assert "<svg" not in prepared.text
    assert prepared.text.count("![](") == 2
    assert "Image 1" not in prepared.text
    assert prepared.text.index(prepared.assets[0].png_path.as_posix()) < prepared.text.index(
        prepared.assets[1].png_path.as_posix()
    )
    for index, asset in enumerate(prepared.assets, start=1):
        assert asset.index == index
        assert asset.svg_path.read_text(encoding="utf-8").startswith("<svg")
        assert asset.png_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        assert f"image_{index:03d}_" in asset.svg_path.name
        assert asset.png_path.as_posix() in prepared.text


def test_repeated_export_reuses_identical_hashed_assets(tmp_path: Path) -> None:
    source = f"Before\n{SVG_ONE}\nAfter"
    output = tmp_path / "same name.odt"

    first = prepare_pandoc_document(source, output)
    second = prepare_pandoc_document(source, output)

    assert first.asset_dir == second.asset_dir
    assert first.assets == second.assets
    assert first.text == second.text


def test_different_document_content_uses_isolated_asset_directories(tmp_path: Path) -> None:
    first = prepare_pandoc_document(f"First\n{SVG_ONE}", tmp_path / "report.docx")
    second = prepare_pandoc_document(f"Second\n{SVG_ONE}", tmp_path / "report.docx")

    assert first.asset_dir is not None
    assert second.asset_dir is not None
    assert first.asset_dir != second.asset_dir


@pytest.mark.parametrize(
    "unsafe_svg",
    [
        "<svg width='10' height='10'><script>alert(1)</script></svg>",
        "<svg width='10' height='10'><image href='https://example.com/x.png'/></svg>",
        "<svg width='10' height='10'><rect onload='alert(1)'/></svg>",
        "<svg width='10' height='10'><style>@import url('https://example.com/x.css');</style></svg>",
    ],
)
def test_unsafe_svg_is_removed_without_creating_assets(tmp_path: Path, unsafe_svg: str) -> None:
    prepared = prepare_pandoc_document(f"Before\n{unsafe_svg}\nAfter", tmp_path / "unsafe.pdf")

    assert prepared.assets == ()
    assert prepared.asset_dir is None
    assert prepared.skipped_svg_count == 1
    assert "<svg" not in prepared.text
    assert "Before" in prepared.text
    assert "After" in prepared.text


def test_incomplete_fenced_svg_is_discarded_without_guessing(tmp_path: Path) -> None:
    source = "Before\n```svg\n<svg width='10' height='10'><rect width='10' height='10'>\n```\nAfter"

    prepared = prepare_pandoc_document(source, tmp_path / "incomplete.pptx")

    assert prepared.assets == ()
    assert prepared.asset_dir is None
    assert prepared.skipped_svg_count == 1
    assert prepared.text == "Before\n\nAfter"


def test_text_without_svg_is_unchanged(tmp_path: Path) -> None:
    source = "Plain Markdown with $x^2$ and `<svg>` as inline code."

    prepared = prepare_pandoc_document(source, tmp_path / "plain.docx")

    assert prepared.text == source
    assert prepared.assets == ()
    assert prepared.asset_dir is None
    assert prepared.skipped_svg_count == 0
