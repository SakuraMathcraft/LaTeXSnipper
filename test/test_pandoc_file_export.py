from pathlib import Path

import pytest
from PyQt6.QtWidgets import QFileDialog

from exporting import pandoc_exporter
from ui import formula_export_menu


@pytest.mark.parametrize("fmt", pandoc_exporter.PANDOC_FORMATS, ids=lambda fmt: fmt.key)
def test_every_pandoc_format_uses_file_export(monkeypatch, fmt):
    calls = []

    def save(*args, **kwargs):
        calls.append((args, kwargs))
        return False, "cancelled"

    def unexpected(*args, **kwargs):
        pytest.fail("Pandoc export entered the clipboard conversion path")

    monkeypatch.setattr(formula_export_menu, "_handle_pandoc_file_export", save)
    monkeypatch.setattr(formula_export_menu, "build_formula_export", unexpected)
    result = formula_export_menu.export_formula_to_clipboard(
        fmt.key,
        "中文 $x$",
        mathml_converter=unexpected,
        omml_converter=unexpected,
        svg_converter=unexpected,
    )
    assert result == (False, "cancelled")
    assert calls[0][0][:2] == (fmt.key, "中文 $x$")


def test_missing_pandoc_skips_save_dialog(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path))

    def unexpected(*args, **kwargs):
        pytest.fail("Missing Pandoc opened the save dialog")

    monkeypatch.setattr(QFileDialog, "getSaveFileName", unexpected)
    assert formula_export_menu._handle_pandoc_file_export(
        "pandoc_plain", "x", "Plain text"
    ) == (False, "")


def test_worker_finishes_silently_if_pandoc_disappears(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path))
    worker = formula_export_menu._PandocFileExportWorker(
        "pandoc_plain", "x", str(tmp_path / "formula.txt"), "Plain text"
    )
    results, errors = [], []
    worker.finished.connect(lambda *args: results.append(args))
    worker.failed.connect(errors.append)

    worker.run()

    assert results == [("", "info")]
    assert not errors


@pytest.mark.parametrize(
    "key,content",
    [
        ("pandoc_html_standalone", "<html><body>中文公式</body></html>"),
        ("pandoc_typst", "中文 $x^2$"),
        ("pandoc_plain", "中文文本\n下一行"),
    ],
)
def test_text_formats_are_saved_as_utf8_files(monkeypatch, tmp_path, key, content):
    monkeypatch.setattr(
        pandoc_exporter, "convert_latex_to", lambda *args, **kwargs: content
    )
    fmt = pandoc_exporter.PANDOC_FORMAT_MAP[key]
    target = tmp_path / ("formula" + fmt.extension)
    worker = formula_export_menu._PandocFileExportWorker(
        key, "x", str(target), fmt.label
    )
    errors = []
    worker.failed.connect(errors.append)
    worker.run()
    assert not errors
    assert Path(target).read_text(encoding="utf-8") == content
