from __future__ import annotations

import pytest

from recognition.pdf_controller import parse_pdf_page_range


@pytest.mark.parametrize(
    ("text", "total_pages", "expected"),
    [
        ("5", 10, (5, 5)),
        ("3-7", 10, (3, 7)),
        (" 3 – 7 ", 10, (3, 7)),
        ("1-1", 1, (1, 1)),
    ],
)
def test_parse_pdf_page_range_accepts_single_page_or_range(
    text: str,
    total_pages: int,
    expected: tuple[int, int],
) -> None:
    assert parse_pdf_page_range(text, total_pages) == expected


@pytest.mark.parametrize("text", ["", "0", "8-3", "1-99", "1-2-3", "a-b"])
def test_parse_pdf_page_range_rejects_invalid_input(text: str) -> None:
    with pytest.raises(ValueError):
        parse_pdf_page_range(text, 10)
