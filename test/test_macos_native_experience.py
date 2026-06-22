from __future__ import annotations

from pathlib import Path

from bootstrap import deps_layer_specs
from runtime import app_paths
from ui.settings_mathcraft_mixin import SettingsMathCraftMixin


ROOT = Path(__file__).resolve().parents[1]


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


def test_macos_screen_recording_denial_is_blocking_and_native() -> None:
    macos_provider = (ROOT / "src" / "backend" / "platform" / "macos_provider.py").read_text(encoding="utf-8")

    assert "PermissionState.DENIED" in macos_provider
    assert "System Settings" in macos_provider
    assert "Privacy & Security" in macos_provider
    assert "Screen Recording" in macos_provider


def test_macos_screen_recording_denial_explains_the_running_permission_target() -> None:
    macos_provider = (ROOT / "src" / "backend" / "platform" / "macos_provider.py").read_text(encoding="utf-8")

    assert "Command+Q" in macos_provider
    assert "/Applications" in macos_provider
    assert "DMG" in macos_provider
    assert "Python" in macos_provider
    assert "Terminal" in macos_provider
    assert "VS Code" in macos_provider


def test_macos_screen_recording_request_requires_a_fresh_app_process() -> None:
    macos_provider = (ROOT / "src" / "backend" / "platform" / "macos_provider.py").read_text(encoding="utf-8")

    assert "requested is True or self._preflight_screen_capture_access() is True" not in macos_provider
    assert "_screen_capture_restart_required" in macos_provider
    assert "授权后请使用 Command+Q 完全退出" in macos_provider


def test_macos_screen_capture_docs_cover_tcc_reset_and_launch_modes() -> None:
    faq = (ROOT / "docs" / "faq.md").read_text(encoding="utf-8")

    assert "tccutil reset ScreenCapture" in faq
    assert "com.mathcraft.latexsnipper" in faq
    assert "Command+Q" in faq
    assert "/Applications" in faq
    assert "DMG" in faq


def test_macos_capture_empty_image_is_not_misreported_as_a_permission_toggle() -> None:
    overlay = (ROOT / "src" / "backend" / "capture_overlay.py").read_text(encoding="utf-8")

    assert "权限已通过预检" in overlay
    assert "截图接口没有返回图像" in overlay
    assert "已允许 LaTeXSnipper" not in overlay


def test_macos_screen_recording_settings_opener_uses_system_preferences_url() -> None:
    macos_provider = (ROOT / "src" / "backend" / "platform" / "macos_provider.py").read_text(encoding="utf-8")

    assert "open_permission_settings" in macos_provider
    assert "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture" in macos_provider


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


def test_macos_native_menu_and_tray_items_are_platform_scoped() -> None:
    macos_provider = (ROOT / "src" / "backend" / "platform" / "macos_provider.py").read_text(encoding="utf-8")
    windows_provider = (ROOT / "src" / "backend" / "platform" / "windows_provider.py").read_text(encoding="utf-8")

    for text in (
        "About LaTeXSnipper",
        "Preferences...",
        "Hide LaTeXSnipper",
        "Hide Others",
        "Quit LaTeXSnipper",
        "Start Capture / Snip",
        "Show Main Window",
    ):
        assert text in macos_provider
        assert text not in windows_provider


def test_macos_hotkey_cleanup_removes_carbon_handler() -> None:
    qhotkey_macos = (ROOT / "src" / "backend" / "qhotkey" / "qhotkey_macos.py").read_text(encoding="utf-8")

    assert "def _remove_handler(self)" in qhotkey_macos
    assert "RemoveEventHandler(self._handler_ref)" in qhotkey_macos
    assert "self._handler_ref = ctypes.c_void_p()" in qhotkey_macos
    assert "self._handler_proc = None" in qhotkey_macos
    assert "self._remove_handler()" in qhotkey_macos


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


def test_macos_packaging_guards_dmg_and_declares_privacy_copy() -> None:
    build_script = (ROOT / "scripts" / "build_macos.sh").read_text(encoding="utf-8")
    spec = (ROOT / "LaTeXSnipper-macos.spec").read_text(encoding="utf-8")

    assert "find \"$DMG_STAGING_DIR\" -mindepth 1 -maxdepth 1" in build_script
    assert "unexpected file in DMG staging directory" in build_script
    assert "NSDocumentsFolderUsageDescription" in spec
    assert "NSDownloadsFolderUsageDescription" in spec
    assert "NSDesktopFolderUsageDescription" in spec


def test_packaging_runtime_is_explicitly_python311() -> None:
    package_common = (ROOT / "scripts" / "package_common.sh").read_text(encoding="utf-8")

    assert "find_python311_command()" in package_common
    assert "PYTHON311" in package_common
    assert "sys.version_info[:2] == (3, 11)" in package_common
    assert "isolated build runtime must be Python 3.11" in package_common
