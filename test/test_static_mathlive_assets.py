# coding: utf-8

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MATHLIVE = ROOT / "src" / "assets" / "mathlive"


def test_desktop_mathlive_editor_uses_local_runtime_assets() -> None:
    app = (MATHLIVE / "app.js").read_text(encoding="utf-8")
    bridge_panel = (MATHLIVE / "bridge_panel.js").read_text(encoding="utf-8")
    combined = app + "\n" + bridge_panel

    assert "https://" not in combined
    assert "http://" not in combined
    assert (MATHLIVE / "vendor" / "mathlive.min.mjs").is_file()
    assert (MATHLIVE / "vendor" / "mathlive.LICENSE.txt").is_file()
    assert (MATHLIVE / "vendor" / "compute-engine.min.esm.js").is_file()
    assert (MATHLIVE / "vendor" / "compute-engine.LICENSE.txt").is_file()
    assert any((MATHLIVE / "vendor" / "fonts").glob("*.woff2"))
