# coding: utf-8

from __future__ import annotations

import io
import zipfile

import pytest

from exporting import pandoc_exporter

SAMPLE_LATEX = (
    r"\frac{d}{dt}\frac{\partial L}{\partial \dot q_i}"
    r"-\frac{\partial L}{\partial q_i}=0"
)


def test_pandoc_format_registry_is_complete() -> None:
    formats = pandoc_exporter.PANDOC_FORMATS
    keys = [fmt.key for fmt in formats]

    assert len(formats) == 18
    assert len(keys) == len(set(keys))
    assert set(keys) == set(pandoc_exporter.PANDOC_FORMAT_MAP)
    assert {fmt.key for fmt in formats if fmt.needs_file} == {
        "pandoc_docx",
        "pandoc_odt",
        "pandoc_epub",
    }
    for fmt in formats:
        assert fmt.key.startswith("pandoc_")
        assert fmt.label
        assert fmt.pandoc_format
        assert fmt.extension.startswith(".")


def test_all_pandoc_export_formats_have_valid_sample_output() -> None:
    if not pandoc_exporter.check_pandoc_available(force=True):
        pytest.skip("Pandoc backend is not installed")

    results: dict[str, str | bytes] = {}
    for fmt in pandoc_exporter.PANDOC_FORMATS:
        result = pandoc_exporter.convert_latex_to(
            fmt.key,
            SAMPLE_LATEX,
            as_document=True,
        )
        results[fmt.key] = result
        if fmt.needs_file:
            assert isinstance(result, bytes), fmt.key
            assert len(result) > 100, fmt.key
            assert result.startswith(b"PK"), fmt.key
        else:
            assert isinstance(result, str), fmt.key
            assert result.strip(), fmt.key

    docx = _read_zip(results["pandoc_docx"])
    assert "word/document.xml" in docx
    assert b"<m:oMath" in docx["word/document.xml"]

    odt = _read_zip(results["pandoc_odt"])
    assert "content.xml" in odt
    assert any(name.endswith("/content.xml") for name in odt if name != "content.xml")

    epub = _read_zip(results["pandoc_epub"])
    assert "EPUB/content.opf" in epub
    assert any(name.endswith((".xhtml", ".html")) for name in epub)

    text = {
        key: value
        for key, value in results.items()
        if isinstance(value, str)
    }
    assert "<html" in text["pandoc_html_standalone"].lower()
    assert "\\[" in text["pandoc_latex"]
    assert "frac(" in text["pandoc_typst"]
    assert "``` math" in text["pandoc_gfm"]
    assert "$$" in text["pandoc_commonmark"]
    assert ".. math::" in text["pandoc_rst"]
    assert '<math display="block">' in text["pandoc_mediawiki"]
    assert "\\[" in text["pandoc_org"]

    for key in {
        "pandoc_icml",
        "pandoc_rtf",
        "pandoc_plain",
        "pandoc_dokuwiki",
        "pandoc_textile",
        "pandoc_jira",
        "pandoc_man",
    }:
        normalized = text[key].lower()
        assert any(token in normalized for token in ("frac", "partial", "math")), key


def _read_zip(result: str | bytes) -> dict[str, bytes]:
    assert isinstance(result, bytes)
    with zipfile.ZipFile(io.BytesIO(result)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}
