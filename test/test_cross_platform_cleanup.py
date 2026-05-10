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
        ROOT / "scripts" / "package_common.sh",
    )
    sources = "\n".join(path.read_text(encoding="utf-8") for path in script_paths)
    assert "src/deps/python311" in sources
    assert "PROJECT_ROOT/python311" not in sources
    assert "grep -oP" not in sources

    macos_spec = (ROOT / "LaTeXSnipper-macos.spec").read_text(encoding="utf-8")
    assert 'else ROOT / "src" / "deps"' in macos_spec


def test_cross_platform_changes_do_not_expand_windows_dependency_surface() -> None:
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    requirements = [line.strip() for line in requirements if line.strip() and not line.startswith("#")]
    assert requirements == [
        "PyQt6==6.10.0",
        "PyQt6-Qt6==6.10.0",
        "PyQt6-WebEngine==6.10.0",
        "PyQt6-WebEngine-Qt6==6.10.0",
        "PyQt6-Fluent-Widgets==1.11.2",
    ]

    build_requirements = (ROOT / "requirements-build.txt").read_text(encoding="utf-8")
    assert "pywin32==311" in build_requirements
    assert "pypandoc==1.17" in build_requirements
    assert "pypandoc>=1.15" not in build_requirements

    for rel_path in ("Inno/latexsnipper.iss", "Inno/latexsnipper_offline.iss"):
        inno = (ROOT / rel_path).read_text(encoding="utf-8")
        assert r"DefaultDirName={localappdata}\{#MyAppName}" in inno
        assert "PrivilegesRequired=lowest" in inno
        assert "PrivilegesRequired=admin" not in inno
        assert r'MessagesFile: "{#MyRepoRoot}\Inno\ChineseSimplified.isl"' in inno
    assert (ROOT / "Inno" / "ChineseSimplified.isl").exists()


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


def test_release_workflow_uses_node24_actions_and_pinned_windows_runner() -> None:
    workflows = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            ROOT / ".github" / "workflows" / "ci.yml",
            ROOT / ".github" / "workflows" / "release.yml",
        )
    )

    assert "actions/checkout@v4" not in workflows
    assert "actions/setup-python@v5" not in workflows
    assert "actions/upload-artifact@v4" not in workflows
    assert "actions/download-artifact@v4" not in workflows
    assert "actions/checkout@v6" in workflows
    assert "actions/setup-python@v6" in workflows
    assert "actions/upload-artifact@v7" in workflows
    assert "actions/download-artifact@v7" in workflows
    assert "runs-on: windows-latest" not in workflows
    assert "runs-on: windows-2025" in workflows


def test_windows_release_normalizes_bundled_python_seed() -> None:
    script = (ROOT / "scripts" / "build_github_release_installer.ps1").read_text(encoding="utf-8")

    assert "function Normalize-BundledPythonSeed" in script
    assert 'Remove-Item -LiteralPath $pyvenvCfg -Force' in script
    assert "python311._pth" in script
    assert "Lib\\site-packages" in script
    assert "$verifyCode = @'" in script
    assert '$verifyCode = @"' not in script
    assert "latexsnipper_verify_python_seed_" in script
    assert "& $pythonExe $verifyScript $seedRoot" in script
    assert "& $pythonExe -c $verifyCode $seedRoot" not in script
    assert "sys.prefix does not point to bundled python311" in script
    assert "sys.path contains paths outside bundled python311" in script
    assert "Normalize-BundledPythonSeed -Root $root" in script
