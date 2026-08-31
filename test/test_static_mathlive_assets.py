# coding: utf-8

from __future__ import annotations

from pathlib import Path
import re


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


def test_mathlive_english_catalog_covers_static_and_dynamic_ui_text() -> None:
    catalog = (MATHLIVE / "i18n.js").read_text(encoding="utf-8")
    catalog_keys = set(re.findall(r"^\s+'([^']+)':", catalog, flags=re.MULTILINE))

    required: set[str] = set()
    for name in ("index.html", "app.js", "bridge_panel.js"):
        source = (MATHLIVE / name).read_text(encoding="utf-8")
        required.update(re.findall(r'data-i18n="([^"]+)"', source))
        required.update(re.findall(r"\bt\('([^']+)'", source))

    assert required <= catalog_keys
