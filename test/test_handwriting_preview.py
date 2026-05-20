from __future__ import annotations

import builtins
import importlib.util
from pathlib import Path
import sys
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_handwriting_latex_preview_keeps_multiline_environment_together() -> None:
    from handwriting.latex_preview import build_handwriting_preview_html, normalize_latex_preview_source

    latex = "\\begin{aligned}\nM_{C lie H Craft}\\\\\n\\int_0^1 x^2 dx\n\\end{aligned}"

    assert normalize_latex_preview_source(latex) == latex

    html = build_handwriting_preview_html(latex, "latex")

    assert "\\begin{aligned}" in html
    assert "\\end{aligned}" in html
    assert '<div class="math-block">' not in html


def test_handwriting_markdown_preview_preserves_text_and_math() -> None:
    from handwriting.latex_preview import build_handwriting_preview_html

    html = build_handwriting_preview_html("京文子\nMathCraft\n$$\\int_0^1 x^2 dx$$", "markdown")

    assert "京文子" in html
    assert "MathCraft" in html
    assert "$$\\int_0^1 x^2 dx$$" in html
    assert "tex-mml-chtml.js" in html


def test_handwriting_external_prompt_preserves_text_and_formula() -> None:
    from backend.external_model.prompts import build_prompt
    from backend.external_model.schemas import ExternalModelConfig

    prompt = build_prompt(
        ExternalModelConfig(
            output_mode="markdown",
            prompt_template="ocr_handwriting_mixed_v1",
        )
    )

    assert "ordinary words" in prompt
    assert "Chinese text" in prompt
    assert "$$...$$" in prompt
    assert "Do not treat ordinary text near formulas as noise" in prompt


def test_handwriting_recognizer_imports_without_numpy() -> None:
    real_import = builtins.__import__

    def blocked_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "numpy" or name.startswith("numpy."):
            raise ImportError("blocked numpy")
        return real_import(name, globals, locals, fromlist, level)

    module_path = SRC / "handwriting" / "recognizer.py"
    spec = importlib.util.spec_from_file_location("handwriting_recognizer_no_numpy", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)

    with mock.patch("builtins.__import__", side_effect=blocked_import):
        spec.loader.exec_module(module)

    assert callable(module.qimage_to_pil)


def test_window_openers_lazy_loads_workbench_window() -> None:
    source = (SRC / "ui" / "window_openers.py").read_text(encoding="utf-8")
    import_section = source.split("class WindowOpenersMixin:", 1)[0]

    assert "from editor.workbench_window import WorkbenchWindow" not in import_section
    assert "from editor.workbench_window import WorkbenchWindow" in source


def test_window_openers_lazy_loads_bilingual_reader() -> None:
    source = (SRC / "ui" / "window_openers.py").read_text(encoding="utf-8")
    import_section = source.split("class WindowOpenersMixin:", 1)[0]

    assert "from handwriting.bilingual_pdf_window import BilingualPdfWindow" not in import_section
    assert "from handwriting.bilingual_pdf_window import BilingualPdfWindow" in source


def test_bilingual_reader_loads_pymupdf_on_demand() -> None:
    source = (SRC / "handwriting" / "bilingual_pdf_window.py").read_text(encoding="utf-8")
    import_section = source.split("@dataclass", 1)[0]

    assert "import fitz" not in import_section
    assert "def _load_fitz_module()" in source
    assert 'import_module("fitz")' in source


def test_handwriting_window_uses_dedicated_external_ocr_defaults() -> None:
    source = (SRC / "handwriting" / "handwriting_window.py").read_text(encoding="utf-8")

    assert 'output_mode="markdown"' in source
    assert 'prompt_template="ocr_handwriting_mixed_v1"' in source


def test_handwriting_internal_recognition_is_fixed_to_mixed_mode() -> None:
    from handwriting.model_policy import resolve_handwriting_recognition_model

    assert resolve_handwriting_recognition_model("mathcraft") == "mathcraft_mixed"
    assert resolve_handwriting_recognition_model("mathcraft_text") == "mathcraft_mixed"
    assert resolve_handwriting_recognition_model("mathcraft_mixed") == "mathcraft_mixed"
    assert resolve_handwriting_recognition_model("external_model") == "external_model"


def test_handwriting_window_uses_shared_model_policy() -> None:
    source = (SRC / "handwriting" / "handwriting_window.py").read_text(encoding="utf-8")

    assert "resolve_handwriting_recognition_model" in source
    assert 'valid = {"mathcraft", "mathcraft_text", "mathcraft_mixed", "external_model"}' not in source


def test_handwriting_window_opener_warms_mixed_without_using_main_preference() -> None:
    source = (SRC / "ui" / "window_openers.py").read_text(encoding="utf-8")

    assert "resolve_handwriting_recognition_model(preferred)" in source
    assert "_warmup_handwriting_model_async(handwriting_model)" in source
    assert "_ensure_model_warmup_async(preferred_model=preferred)" not in source


def test_handwriting_window_uses_lightweight_line_number_editor() -> None:
    source = (SRC / "handwriting" / "handwriting_window.py").read_text(encoding="utf-8")
    import_section = source.split("class _HandwritingDocumentLayoutWorker", 1)[0]

    assert "from .editor_widgets import HandwritingPlainTextEdit" in import_section
    assert "PreviewPlainTextEdit = HandwritingPlainTextEdit" in source
    assert "from .document_preview_window import" not in import_section


def test_wrap_tex_document_normalizes_external_article_document() -> None:
    from handwriting.tex_document_utils import wrap_tex_document

    wrapped = wrap_tex_document(
        "\\documentclass{article}\n"
        "\\usepackage{amsmath}\n"
        "\\begin{document}\n"
        "MathCraft\n"
        "$$\\int_0^1 \\Gamma(x) dx$$\n"
        "\\end{document}"
    )

    assert "\\documentclass[UTF8]{ctexart}" in wrapped
    assert "\\documentclass{article}" not in wrapped
    assert "\\usepackage{amsmath,amssymb,amsthm,mathtools,bm}" in wrapped
    assert "\\usepackage{geometry}" in wrapped
    assert "\\geometry{a4paper,margin=2.2cm}" in wrapped
    assert "\\[\n\\int_0^1 \\Gamma(x) dx\n\\]" in wrapped
    assert wrapped.count("\\begin{document}") == 1
    assert wrapped.count("\\end{document}") == 1


def test_wrap_tex_document_preserves_plain_text_lines_as_paragraphs() -> None:
    from handwriting.tex_document_utils import wrap_tex_document

    wrapped = wrap_tex_document(
        "Hello\n"
        "MathCraft\n"
        "$$\\int_0^1 \\Gamma(x) dx$$"
    )

    body = wrapped.split("\\begin{document}", 1)[1].split("\\end{document}", 1)[0]
    assert "Hello\n\nMathCraft" in body
    assert "\\[\n\\int_0^1 \\Gamma(x) dx\n\\]" in body


def test_wrap_tex_document_completes_external_partial_document() -> None:
    from handwriting.tex_document_utils import wrap_tex_document

    wrapped = wrap_tex_document(
        "\\documentclass{article}\n"
        "\\usepackage{amsmath}\n"
        "\\begin{document}\n"
        "\\int_0^1 x^2 dx"
    )

    assert wrapped.startswith("\\documentclass[UTF8]{ctexart}")
    assert "\\end{document}" in wrapped


def test_merge_layout_with_recognized_draft_restores_dropped_text() -> None:
    from handwriting.tex_document_utils import merge_layout_with_recognized_draft

    merged = merge_layout_with_recognized_draft(
        "\\documentclass[UTF8]{ctexart}\n"
        "\\begin{document}\n"
        "Math\n"
        "\\[\n"
        "\\int_0^1 \\Gamma(x) dx\n"
        "\\]\n"
        "\\end{document}",
        "MathCraft\n$$\\int_0^1 \\Gamma(x) dx$$",
    )

    body = merged.split("\\begin{document}", 1)[1].split("\\end{document}", 1)[0]
    assert "MathCraft" in body
    assert "\nMath\n" not in body
    assert "\\int_0^1 \\Gamma(x) dx" in body


def test_merge_layout_with_recognized_draft_keeps_existing_text_once() -> None:
    from handwriting.tex_document_utils import merge_layout_with_recognized_draft

    merged = merge_layout_with_recognized_draft(
        "\\documentclass[UTF8]{ctexart}\n"
        "\\begin{document}\n"
        "MathCraft\n"
        "\\[\n"
        "x^2\n"
        "\\]\n"
        "\\end{document}",
        "MathCraft\n$$x^2$$",
    )

    assert merged.count("MathCraft") == 1


def test_merge_layout_with_recognized_draft_preserves_multiple_text_lines() -> None:
    from handwriting.tex_document_utils import merge_layout_with_recognized_draft

    merged = merge_layout_with_recognized_draft(
        "\\documentclass[UTF8]{ctexart}\n"
        "\\begin{document}\n"
        "\\[\n"
        "\\int_0^1 \\Gamma(x) dx\n"
        "\\]\n"
        "\\end{document}",
        "Hello\nMathCraft\n$$\\int_0^1 \\Gamma(x) dx$$",
    )

    body = merged.split("\\begin{document}", 1)[1].split("\\end{document}", 1)[0]
    assert "Hello\n\nMathCraft" in body
