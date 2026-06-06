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
    snippets = (ROOT / "src" / "editor" / "latex_snippet_panel.py").read_text(encoding="utf-8")

    assert "mathfield.mode === 'latex'" in app
    assert "mathfield.executeCommand('addRowAfter')" in app
    assert "const VISIBLE_MATH_SPACE = '\\\\,';" in app
    assert "mathfield.mathModeSpace = VISIBLE_MATH_SPACE;" in app
    assert "const MULTILINE_TEMPLATE = '\\\\begin{aligned}#@\\\\\\\\#?\\\\end{aligned}';" in app
    assert "event.stopImmediatePropagation();" in app
    assert "insertToMain();" in app
    assert "hideVirtualKeyboard" in app
    assert "previousSuggestion" not in app
    assert "nextSuggestion" not in app
    assert "getCompletionPopup" not in app
    assert "moveToPreviousChar" not in app
    assert "moveToNextChar" not in app
    assert "moveUp" not in app
    assert "moveDown" not in app
    assert "换行  (Enter)" in snippets
    assert "换行  (Shift+Enter)" not in snippets
