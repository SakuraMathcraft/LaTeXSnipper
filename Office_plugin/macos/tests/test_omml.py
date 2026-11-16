from __future__ import annotations

import pytest
from latexsnipper_office import omml
from latexsnipper_office.omml import MATH, WORD, apply_typography
from latexsnipper_office.typography import Typography
from lxml import etree

OMML = (
    f'<m:oMath xmlns:m="{MATH}" xmlns:w="{WORD}">'
    "<m:r><m:t>12</m:t></m:r>"
    "<m:r><m:t>x</m:t></m:r>"
    "<m:r><m:rPr><m:nor/></m:rPr><m:t>中文</m:t></m:r>"
    '<m:r><w:rPr><w:color w:val="FF0000"/></w:rPr><m:t>y</m:t></m:r>'
    "</m:oMath>"
)


def runs(omml):
    root = etree.fromstring(omml.encode())
    result = []
    for run in root.iter(f"{{{MATH}}}r"):
        properties = run.find(f"{{{WORD}}}rPr")
        fonts = properties.find(f"{{{WORD}}}rFonts")
        result.append(
            {
                "text": "".join(run.itertext()),
                "ascii": fonts.get(f"{{{WORD}}}ascii"),
                "eastAsia": fonts.get(f"{{{WORD}}}eastAsia"),
                "color": properties.find(f"{{{WORD}}}color").get(f"{{{WORD}}}val"),
                "size": properties.find(f"{{{WORD}}}sz").get(f"{{{WORD}}}val"),
            }
        )
    return result


def test_applies_symbol_number_and_cjk_fonts_like_windows():
    typography = Typography(
        symbol_font_id="mathjax-stix2",
        number_font_family="Arial",
        cjk_font_family="Songti SC",
        font_size_points=10.5,
        color="#123456",
    )
    result = runs(apply_typography(OMML, typography))
    assert [run["ascii"] for run in result] == [
        "Arial",
        "STIX Two Math",
        "Times New Roman",
        "STIX Two Math",
    ]
    assert {run["eastAsia"] for run in result} == {"Songti SC"}
    assert {run["size"] for run in result} == {"21"}
    # Source-local color emitted by the converter wins over the default color.
    assert [run["color"] for run in result] == ["123456", "123456", "123456", "FF0000"]


def test_numbers_follow_symbol_font_without_number_family():
    assert runs(apply_typography(OMML, Typography()))[0]["ascii"] == "Cambria Math"


def test_rejects_non_omml_roots():
    with pytest.raises(ValueError):
        apply_typography("<root/>", Typography())


def test_finds_stylesheet_inside_word_for_mac(monkeypatch, tmp_path):
    system, user = tmp_path / "Applications", tmp_path / "home/Applications"
    stylesheet = user / omml.WORD_STYLESHEET
    stylesheet.parent.mkdir(parents=True)
    stylesheet.touch()
    monkeypatch.setattr(omml, "application_directories", lambda: (system, user))
    assert omml.find_stylesheet() == stylesheet
    stylesheet.unlink()
    assert omml.find_stylesheet() is None
    with pytest.raises(omml.StylesheetUnavailable):
        omml.mathml_to_omml(
            "<math xmlns='http://www.w3.org/1998/Math/MathML'><mi>x</mi></math>"
        )


@pytest.mark.skipif(
    omml.find_stylesheet() is None, reason="Microsoft Word is not installed"
)
def test_converts_with_installed_word_and_repairs_empty_nary():
    mathml = (
        "<math xmlns='http://www.w3.org/1998/Math/MathML'>"
        "<munderover><mo>&#x2211;</mo><mi>k</mi><mi>n</mi></munderover><mi>k</mi></math>"
    )
    converted = omml.convert(mathml, Typography())
    root = etree.fromstring(converted.encode())
    nary = root.find(f".//{{{MATH}}}nary")
    assert nary is not None
    assert "".join(nary.find(f"{{{MATH}}}e").itertext()) == "k"
