# coding: utf-8

from __future__ import annotations

import io
import sys
import types
import zipfile
from pathlib import Path

import pytest

from exporting import pandoc_exporter

SAMPLE_LATEX = (
    r"\frac{d}{dt}\frac{\partial L}{\partial \dot q_i}"
    r"-\frac{\partial L}{\partial q_i}=0"
)

MIXED_PROBLEM_DOCUMENT = r"""
# 数学与物理综合题 / Mixed Math and Physics Problems

## 题目 1：受迫振动

A particle with mass $m$ satisfies the differential equation

$$
m\frac{d^2x}{dt^2}+c\frac{dx}{dt}+kx=F_0\cos(\omega t).
$$

请说明当 $\omega \approx \sqrt{k/m}$ 时振幅为什么会增大，并给出稳态解的相位差。

## Problem 2: Vector calculus

For the vector field $\mathbf{F}(x,y,z)=(-y,x,z^2)$, compute

$$
\nabla\times\mathbf{F}
=\begin{pmatrix}
\partial_y z^2-\partial_z x\\
\partial_z(-y)-\partial_x z^2\\
\partial_x x-\partial_y(-y)
\end{pmatrix}.
$$

再判断曲线积分 $\oint_C \mathbf{F}\cdot d\mathbf{r}$ 是否可用 Stokes 定理化为面积分。

## 题目 3：概率

若随机变量 $X\sim N(\mu,\sigma^2)$，证明标准化变量
$Z=(X-\mu)/\sigma$ 满足 $Z\sim N(0,1)$。
""".strip()


def test_pandoc_format_registry_is_complete() -> None:
    formats = pandoc_exporter.PANDOC_FORMATS
    keys = [fmt.key for fmt in formats]

    assert len(formats) == 8
    assert len(keys) == len(set(keys))
    assert set(keys) == set(pandoc_exporter.PANDOC_FORMAT_MAP)
    assert {fmt.key for fmt in formats if fmt.needs_file} == {
        "pandoc_docx",
        "pandoc_odt",
        "pandoc_pptx",
        "pandoc_epub",
        "pandoc_pdf",
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
            if fmt.key == "pandoc_pdf":
                assert result.startswith(b"%PDF-"), fmt.key
            else:
                assert result.startswith(b"PK"), fmt.key
        else:
            assert isinstance(result, str), fmt.key
            assert result.strip(), fmt.key

    docx = _read_zip(results["pandoc_docx"])
    assert "word/document.xml" in docx
    assert b"<m:oMath" in docx["word/document.xml"]

    odt = _read_zip(results["pandoc_odt"])
    assert "content.xml" in odt

    epub = _read_zip(results["pandoc_epub"])
    assert "EPUB/content.opf" in epub
    assert any(name.endswith((".xhtml", ".html")) for name in epub)

    text = {
        key: value
        for key, value in results.items()
        if isinstance(value, str)
    }
    assert "<html" in text["pandoc_html_standalone"].lower()
    assert "mathjax" in text["pandoc_html_standalone"].lower()
    assert "frac" in text["pandoc_plain"]

    for key in {"pandoc_plain"}:
        normalized = text[key].lower()
        assert any(token in normalized for token in ("frac", "partial", "math")), key


def test_plain_text_is_not_wrapped_as_display_math() -> None:
    if not pandoc_exporter.check_pandoc_available(force=True):
        pytest.skip("Pandoc backend is not installed")

    result = pandoc_exporter.convert_latex_to(
        "pandoc_typst",
        "Theorem 2.1 states that compact metric spaces behave well.",
        as_document=True,
    )

    assert isinstance(result, str)
    assert result.startswith("Theorem 2.1")
    assert "$ T h e o r e m" not in result


def test_real_world_mixed_problem_exports_are_structured() -> None:
    if not pandoc_exporter.check_pandoc_available(force=True):
        pytest.skip("Pandoc backend is not installed")

    html = pandoc_exporter.convert_latex_to(
        "pandoc_html_standalone",
        MIXED_PROBLEM_DOCUMENT,
        as_document=True,
    )
    assert isinstance(html, str)
    assert "受迫振动" in html
    assert "Mixed Math and Physics Problems" in html
    assert "mathjax" in html.lower()
    assert "nabla" in html or "∇" in html

    docx = _read_zip(
        pandoc_exporter.convert_latex_to(
            "pandoc_docx",
            MIXED_PROBLEM_DOCUMENT,
            as_document=True,
        )
    )
    assert "word/document.xml" in docx
    assert "受迫振动".encode("utf-8") in docx["word/document.xml"]
    assert b"<m:oMath" in docx["word/document.xml"]

    pptx = _read_zip(
        pandoc_exporter.convert_latex_to(
            "pandoc_pptx",
            MIXED_PROBLEM_DOCUMENT,
            as_document=True,
        )
    )
    slide_xml = b"\n".join(value for name, value in pptx.items() if name.startswith("ppt/slides/slide"))
    assert "Mixed Math and Physics Problems".encode("utf-8") in slide_xml
    assert "受迫振动".encode("utf-8") in slide_xml

    pdf = pandoc_exporter.convert_latex_to(
        "pandoc_pdf",
        MIXED_PROBLEM_DOCUMENT,
        as_document=True,
    )
    assert isinstance(pdf, bytes)
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 1000


def test_pdf_export_returns_generated_pdf_after_pandoc_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pypandoc = types.SimpleNamespace()

    def convert_text(*args: object, outputfile: str, **kwargs: object) -> None:
        Path(outputfile).write_bytes(b"%PDF-1.7\npartial pdf")
        raise RuntimeError("LaTeX returned a non-zero exit code")

    fake_pypandoc.convert_text = convert_text
    monkeypatch.setitem(sys.modules, "pypandoc", fake_pypandoc)
    monkeypatch.setattr(pandoc_exporter, "is_available", lambda: True)
    monkeypatch.setattr(pandoc_exporter, "_find_pdf_engine", lambda: "xelatex")

    result = pandoc_exporter.convert_latex_to("pandoc_pdf", r"\frac{1}{x}")

    assert result == b"%PDF-1.7\npartial pdf"


def test_pdf_export_rejects_invalid_file_after_pandoc_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pypandoc = types.SimpleNamespace()

    def convert_text(*args: object, outputfile: str, **kwargs: object) -> None:
        Path(outputfile).write_bytes(b"not a pdf")
        raise RuntimeError("LaTeX returned a non-zero exit code")

    fake_pypandoc.convert_text = convert_text
    monkeypatch.setitem(sys.modules, "pypandoc", fake_pypandoc)
    monkeypatch.setattr(pandoc_exporter, "is_available", lambda: True)
    monkeypatch.setattr(pandoc_exporter, "_find_pdf_engine", lambda: "xelatex")

    with pytest.raises(pandoc_exporter.PandocConversionError):
        pandoc_exporter.convert_latex_to("pandoc_pdf", r"\frac{1}{x}")


def test_non_pdf_file_export_still_fails_after_pandoc_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pypandoc = types.SimpleNamespace()

    def convert_text(*args: object, outputfile: str, **kwargs: object) -> None:
        Path(outputfile).write_bytes(b"PK\x03\x04partial zip")
        raise RuntimeError("Pandoc returned a non-zero exit code")

    fake_pypandoc.convert_text = convert_text
    monkeypatch.setitem(sys.modules, "pypandoc", fake_pypandoc)
    monkeypatch.setattr(pandoc_exporter, "is_available", lambda: True)

    with pytest.raises(pandoc_exporter.PandocConversionError):
        pandoc_exporter.convert_latex_to("pandoc_docx", r"\frac{1}{x}")


def _read_zip(result: str | bytes) -> dict[str, bytes]:
    assert isinstance(result, bytes)
    with zipfile.ZipFile(io.BytesIO(result)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}
