from __future__ import annotations

from bootstrap import deps_layer_specs
from runtime import app_paths
from ui.settings_mathcraft_mixin import SettingsMathCraftMixin


def test_macos_app_paths_use_library_directories(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(app_paths.sys, "platform", "darwin")
    monkeypatch.setattr(app_paths.pathlib.Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(app_paths, "_APP_STATE_DIR_CACHE", None)
    monkeypatch.setattr(app_paths, "_APP_LOG_DIR_CACHE", None)

    assert app_paths.app_state_dir() == tmp_path / "Library" / "Application Support" / "LaTeXSnipper"
    assert app_paths.app_cache_dir() == tmp_path / "Library" / "Caches" / "LaTeXSnipper"
    assert app_paths.app_log_dir() == tmp_path / "Library" / "Logs" / "LaTeXSnipper"
    assert app_paths.app_config_path() == (
        tmp_path / "Library" / "Application Support" / "LaTeXSnipper" / "LaTeXSnipper_config.json"
    )


def test_macos_dependency_gpu_probe_does_not_run_cuda_tools(monkeypatch) -> None:
    def fail_run(*_args, **_kwargs):
        raise AssertionError("macOS dependency UI must not probe nvidia-smi or nvcc")

    monkeypatch.setattr(deps_layer_specs.sys, "platform", "darwin")
    monkeypatch.setattr(deps_layer_specs.subprocess, "run", fail_run)

    assert deps_layer_specs._gpu_available() is False
    assert deps_layer_specs._cuda_toolkit_available() is False


def test_macos_settings_device_probe_does_not_run_windows_or_nvidia_tools(monkeypatch) -> None:
    def fail_run(*_args, **_kwargs):
        raise AssertionError("macOS settings page must not run powershell or nvidia-smi")

    monkeypatch.setattr("ui.settings_mathcraft_mixin.sys.platform", "darwin")
    monkeypatch.setattr("ui.settings_mathcraft_mixin.subprocess.run", fail_run)

    assert SettingsMathCraftMixin()._probe_local_device_names() == ("", "")


def test_macos_dependency_wizard_hides_nvidia_cuda_gpu_option(monkeypatch) -> None:
    from bootstrap import deps_ui

    monkeypatch.setattr(deps_ui.sys, "platform", "darwin")

    assert "MATHCRAFT_GPU" not in deps_ui._visible_layer_names()
    assert "MATHCRAFT_CPU" in deps_ui._visible_layer_names()


def test_macos_dependency_wizard_does_not_show_gpu_explainer_copy(monkeypatch) -> None:
    from bootstrap import deps_ui

    monkeypatch.setattr(deps_ui.sys, "platform", "darwin")

    text = deps_ui._layer_description_text()
    assert "MATHCRAFT_GPU" not in text
    assert "NVIDIA" not in text
    assert "CUDA" not in text


def test_macos_dependency_failure_guidance_avoids_windows_terminal_copy(monkeypatch) -> None:
    from bootstrap import deps_workers

    monkeypatch.setattr(deps_workers.sys, "platform", "darwin")

    text = "\n".join(deps_workers._install_failure_guidance(["lxml~=4.9.3"], 1, 2))

    assert "CMD" not in text
    assert "管理员" not in text
    assert "pip install" not in text
    assert "Python 3.11" in text
    assert "重试" in text


def test_macos_dependency_failure_dialog_is_localized(monkeypatch) -> None:
    from bootstrap import deps_entry

    monkeypatch.setattr(deps_entry.sys, "platform", "darwin")

    title, message = deps_entry._install_failure_dialog_copy()

    assert title == "依赖安装未完成"
    assert "Some dependencies failed" not in message
    assert "Python 3.11" in message


def test_macos_dependency_failure_log_line_is_localized(monkeypatch) -> None:
    from bootstrap import deps_entry

    monkeypatch.setattr(deps_entry.sys, "platform", "darwin")

    text = deps_entry._install_failure_log_line()

    assert "Install has failures" not in text
    assert "依赖安装未完成" in text
