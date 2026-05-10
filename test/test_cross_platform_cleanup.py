# coding: utf-8

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_dependency_wizard_does_not_manage_system_screenshot_packages() -> None:
    bootstrap = (ROOT / "src" / "bootstrap" / "deps_bootstrap.py").read_text(encoding="utf-8")
    screenshot_tools = (ROOT / "src" / "cross_platform" / "screenshot_tools.py").read_text(encoding="utf-8")
    capture_overlay = (ROOT / "src" / "backend" / "capture_overlay.py").read_text(encoding="utf-8")

    assert '"SCREENSHOT"' not in bootstrap
    assert "#system:" not in bootstrap
    assert "install_screenshot_tools" not in bootstrap
    assert "uninstall_screenshot_tools" not in bootstrap
    assert "sudo" not in screenshot_tools
    assert "apt-get" not in screenshot_tools
    assert "pacman" not in screenshot_tools
    assert "capture_region_with_tools" in capture_overlay
    assert "wayland_overlay_background" in capture_overlay
    for tool_name in ("grim", "maim", "gnome-screenshot", "screencapture"):
        assert tool_name in screenshot_tools


def test_cross_platform_packaging_docs_do_not_reference_missing_scripts() -> None:
    readme = (ROOT / "readme.md").read_text(encoding="utf-8")

    referenced_paths = (
        "scripts/build_deb.sh",
        "scripts/build_deb_offline.sh",
        "scripts/build_macos.sh",
        "LaTeXSnipper-linux.spec",
        "LaTeXSnipper-linux-offline.spec",
        "LaTeXSnipper-macos.spec",
        "packaging/debian",
    )
    for rel_path in referenced_paths:
        if rel_path in readme:
            assert (ROOT / rel_path).exists()


def test_cross_platform_build_scripts_use_project_dependency_runtime() -> None:
    script_paths = (
        ROOT / "scripts" / "build_deb.sh",
        ROOT / "scripts" / "build_deb_offline.sh",
        ROOT / "scripts" / "build_macos.sh",
    )
    for path in script_paths:
        source = path.read_text(encoding="utf-8")
        assert 'PYTHON311_DIR="$PROJECT_ROOT/src/deps/python311"' in source
        assert 'PYTHON311_DIR="$PROJECT_ROOT/python311"' not in source
        assert "grep -oP" not in source

    macos_spec = (ROOT / "LaTeXSnipper-macos.spec").read_text(encoding="utf-8")
    assert 'else ROOT / "src" / "deps"' in macos_spec


def test_platform_protocols_cover_main_window_provider_calls() -> None:
    protocols = (ROOT / "src" / "backend" / "platform" / "protocols.py").read_text(encoding="utf-8")

    for method_name in (
        "activated",
        "create_overlay",
        "create_tray",
        "set_tray_tooltip",
        "update_tray_menu",
        "show_notification",
        "activate_window",
    ):
        assert method_name in protocols
