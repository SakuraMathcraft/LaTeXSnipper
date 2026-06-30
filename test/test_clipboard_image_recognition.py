from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_main_window_pastes_clipboard_images_into_existing_recognition_flow() -> None:
    file_drop = (ROOT / "src" / "ui" / "file_drop.py").read_text(encoding="utf-8")
    capture = (ROOT / "src" / "capture" / "capture_controller.py").read_text(encoding="utf-8")

    assert "QKeySequence.StandardKey.Paste" in file_drop
    assert "mime.hasImage()" in file_drop
    assert "qimage_to_rgb_pil(image)" in file_drop
    assert "self._start_predict_with_pil" in file_drop
    assert "self._recognize_image_file(paths[0])" in file_drop
    assert "self._handle_clipboard_image_paste(event)" in capture


def test_macos_paste_menu_routes_images_to_the_existing_recognition_flow() -> None:
    lifecycle = (ROOT / "src" / "ui" / "app_lifecycle_controller.py").read_text(encoding="utf-8")
    macos_provider = (ROOT / "src" / "backend" / "platform" / "macos_provider.py").read_text(encoding="utf-8")
    protocols = (ROOT / "src" / "backend" / "platform" / "protocols.py").read_text(encoding="utf-8")

    assert "on_paste: Callable[[], bool] | None = None" in protocols
    assert "on_paste=self._handle_latex_editor_image_paste" in lifecycle
    assert "def _handle_latex_editor_image_paste(self) -> bool:" in lifecycle
    assert "self._add_paste_action(edit_menu, handlers.on_paste)" in macos_provider
    assert "self._trigger_paste(image_paste_handler)" in macos_provider
    assert "self._trigger_focused_widget_method(\"paste\")" in macos_provider


def test_export_dependencies_use_bundled_mathjax_instead_of_python_renderers() -> None:
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    layers = (ROOT / "src" / "bootstrap" / "deps_layer_specs.py").read_text(encoding="utf-8").lower()
    specs = "\n".join(
        (ROOT / name).read_text(encoding="utf-8").lower()
        for name in ("LaTeXSnipper.spec", "LaTeXSnipper-macos.spec", "LaTeXSnipper-linux.spec")
    )
    converters = (ROOT / "src" / "exporting" / "formula_converters.py").read_text(encoding="utf-8")
    mathjax = (ROOT / "src" / "exporting" / "mathjax_converter.py").read_text(encoding="utf-8")

    assert "latex2mathml" not in requirements
    assert "matplotlib" not in requirements
    assert "latex2mathml" not in layers
    assert "matplotlib" not in layers
    assert "latex2mathml" not in specs
    assert "matplotlib" not in specs
    assert "convert_latex_with_mathjax" in converters
    assert "tex-mml-svg.js" in mathjax
    for package in (
        "action",
        "amscd",
        "bbox",
        "boldsymbol",
        "braket",
        "bussproofs",
        "cancel",
        "cases",
        "centernot",
        "color",
        "colortbl",
        "configmacros",
        "empheq",
        "enclose",
        "extpfeil",
        "gensymb",
        "html",
        "mathtools",
        "mhchem",
        "physics",
        "setoptions",
        "tagformat",
        "textcomp",
        "textmacros",
        "unicode",
        "upgreek",
        "verb",
    ):
        assert f"'[tex]/{package}'" in mathjax
        assert f"'{package}'" in mathjax
    assert "'[tex]/noerrors'" not in mathjax
    assert "'[tex]/noundefined'" not in mathjax
    assert "'[tex]/colorv2'" not in mathjax
    assert "'[tex]/require'" not in mathjax
