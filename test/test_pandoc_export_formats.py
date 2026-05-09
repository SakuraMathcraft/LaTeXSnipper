# coding: utf-8

from __future__ import annotations

import pytest

from exporting import pandoc_exporter


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


def test_all_pandoc_export_formats_convert_when_backend_is_available() -> None:
    if not pandoc_exporter.check_pandoc_available(force=True):
        pytest.skip("Pandoc backend is not installed")

    latex = r"E = mc^2 + \frac{a}{b}"
    for fmt in pandoc_exporter.PANDOC_FORMATS:
        result = pandoc_exporter.convert_latex_to(fmt.key, latex, as_document=True)
        if fmt.needs_file:
            assert isinstance(result, bytes), fmt.key
            assert len(result) > 100, fmt.key
            assert result.startswith(b"PK"), fmt.key
        else:
            assert isinstance(result, str), fmt.key
            assert result.strip(), fmt.key
