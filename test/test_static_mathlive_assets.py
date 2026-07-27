# coding: utf-8

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MATHLIVE = ROOT / "src" / "assets" / "mathlive"


def test_desktop_mathlive_editor_uses_local_runtime_assets() -> None:
    app = (MATHLIVE / "app.js").read_text(encoding="utf-8")
    bridge_panel = (MATHLIVE / "bridge_panel.js").read_text(encoding="utf-8")
    combined = app + "\n" + bridge_panel

    assert "https://esm.run" not in combined
    assert "cdn.jsdelivr.net/npm/mathlive" not in combined
    assert "import('./vendor/mathlive.min.mjs')" in app
    assert "import('./vendor/mathlive.min.mjs')" in bridge_panel
    assert "import('./vendor/compute-engine.min.esm.js')" in app
    assert "new URL('./vendor/fonts', window.location.href).href" in combined
    assert "vendor/vendor/fonts" not in combined
    assert (MATHLIVE / "vendor" / "mathlive.min.mjs").is_file()
    assert (MATHLIVE / "vendor" / "mathlive.LICENSE.txt").is_file()
    assert (MATHLIVE / "vendor" / "compute-engine.min.esm.js").is_file()
    assert (MATHLIVE / "vendor" / "compute-engine.LICENSE.txt").is_file()
    assert any((MATHLIVE / "vendor" / "fonts").glob("*.woff2"))


def test_workbench_uses_current_mathlive_keyboard_policy() -> None:
    app = (MATHLIVE / "app.js").read_text(encoding="utf-8")
    keyboard = (MATHLIVE / "mathfield-keyboard.js").read_text(encoding="utf-8")

    assert "routeMathfieldNavigationKey(mathfield, event)" in app
    assert "ArrowLeft: 'moveToPreviousChar'" in keyboard
    assert "ArrowRight: 'moveToNextChar'" in keyboard
    assert "ArrowUp: 'moveUp'" in keyboard
    assert "ArrowDown: 'moveDown'" in keyboard
    assert "ArrowUp: 'previousSuggestion'" in keyboard
    assert "ArrowDown: 'nextSuggestion'" in keyboard
    assert "mathfield.mode === 'latex'" in keyboard
    assert "mathfield.mode === 'latex'" in app
    assert "mathfield.executeCommand('addRowAfter')" in app
    assert "const VISIBLE_MATH_SPACE = '\\\\,';" in app
    assert "mathfield.mathModeSpace = VISIBLE_MATH_SPACE;" in app
    assert "const MULTILINE_TEMPLATE = '\\\\begin{aligned}#@\\\\\\\\#?\\\\end{aligned}';" in app
    assert "event.stopImmediatePropagation();" in app
    assert "insertToMain();" in app
    assert "hideVirtualKeyboard" in app
    assert "getCompletionPopup" not in app


def test_document_editor_matches_shared_mathlive_keyboard_behavior() -> None:
    bridge_panel = (MATHLIVE / "bridge_panel.js").read_text(encoding="utf-8")
    preview_window = (
        ROOT / "src" / "handwriting" / "document_preview_window.py"
    ).read_text(encoding="utf-8")

    assert "routeMathfieldNavigationKey(mathfield, event)" in bridge_panel
    assert "event.key === 'Escape'" in bridge_panel
    assert "hideVirtualKeyboard();" in bridge_panel
    assert "mathfield.executeCommand('addRowAfter')" in bridge_panel
    assert "mathfield.mathModeSpace = VISIBLE_MATH_SPACE;" in bridge_panel
    assert "event.stopImmediatePropagation();" in bridge_panel
    assert 'QShortcut(QKeySequence("Esc"), self.editor_search_bar)' in preview_window
    assert "Qt.ShortcutContext.WidgetWithChildrenShortcut" in preview_window
