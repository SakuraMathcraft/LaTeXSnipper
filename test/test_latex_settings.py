from __future__ import annotations

import pytest

import rendering.latex as renderer_module


class _ConfigStore:
    def __init__(self, values: dict[str, object] | None = None) -> None:
        self.values = dict(values or {})
        self.saved: list[dict[str, object]] = []

    def get(self, key: str, default=None):
        return self.values.get(key, default)

    def set_many(self, values: dict) -> None:
        update = dict(values)
        self.saved.append(update)
        self.values.update(update)


def _isolate_renderer_settings(monkeypatch) -> None:
    monkeypatch.setattr(renderer_module, "_latex_config", None)
    monkeypatch.setattr(renderer_module, "_latex_renderer", None)


def test_latex_preferences_share_one_config_write(monkeypatch) -> None:
    _isolate_renderer_settings(monkeypatch)
    config = _ConfigStore()
    renderer_module.configure_latex_settings(config)

    renderer_module.update_latex_settings(
        render_mode="latex_pdflatex",
        executable_path=" /usr/bin/pdflatex ",
    )

    assert config.saved == [
        {
            "latex_render_mode": "latex_pdflatex",
            "latex_executable_path": "/usr/bin/pdflatex",
        }
    ]
    assert renderer_module.get_document_render_mode() == "latex_pdflatex"
    assert renderer_module.get_latex_executable_path() == "/usr/bin/pdflatex"


def test_unchanged_latex_preferences_are_not_written(monkeypatch) -> None:
    _isolate_renderer_settings(monkeypatch)
    config = _ConfigStore(
        {
            "latex_render_mode": "mathjax_local",
            "latex_executable_path": "",
        }
    )
    renderer_module.configure_latex_settings(config)

    renderer_module.update_latex_settings(
        render_mode="mathjax_local",
        executable_path="",
    )

    assert config.saved == []


def test_invalid_latex_render_mode_is_rejected(monkeypatch) -> None:
    _isolate_renderer_settings(monkeypatch)
    config = _ConfigStore()
    renderer_module.configure_latex_settings(config)

    with pytest.raises(ValueError, match="无效的公式渲染模式"):
        renderer_module.update_latex_settings(render_mode="legacy")

    assert config.saved == []
