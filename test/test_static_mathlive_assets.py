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
