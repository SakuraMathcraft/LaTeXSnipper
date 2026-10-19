# ruff: noqa: E402

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from runtime import pandoc_runtime


def test_development_pandoc_uses_path(tmp_path, monkeypatch):
    pandoc = tmp_path / "pandoc"
    monkeypatch.setattr(pandoc_runtime, "installed_resources", lambda: None)
    monkeypatch.setattr(pandoc_runtime.shutil, "which", lambda name: str(pandoc))
    assert pandoc_runtime.resolve_pandoc() == pandoc


def test_packaged_pandoc_uses_fixed_runtime_resource(tmp_path, monkeypatch):
    from test_installed_resources import installed

    resources = installed(tmp_path, monkeypatch)
    monkeypatch.setattr(pandoc_runtime, "installed_resources", lambda: resources)
    assert pandoc_runtime.resolve_pandoc() == tmp_path / "runtime/pandoc/pandoc.exe"
    (tmp_path / "runtime/pandoc/pandoc.exe").unlink()
    import pytest

    with pytest.raises(FileNotFoundError):
        pandoc_runtime.resolve_pandoc()


def test_pandoc_exporter_reports_unavailable_without_a_binary(monkeypatch) -> None:
    from exporting import pandoc_exporter

    monkeypatch.setattr(
        pandoc_exporter.importlib.util, "find_spec", lambda _name: object()
    )
    monkeypatch.setattr(pandoc_exporter, "_find_pandoc_binary", lambda: None)

    assert not pandoc_exporter.check_pandoc_available(force=True)
