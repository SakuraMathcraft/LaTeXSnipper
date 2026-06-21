# coding: utf-8

from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
BOM_CHECK_ROOTS = (
    ".github",
    "docs",
    "Inno",
    "office_plugin",
    "packaging",
    "scripts",
    "src",
    "test",
    "user_manual",
)
BOM_CHECK_EXTENSIONS = {
    ".bat",
    ".cmd",
    ".cs",
    ".csproj",
    ".css",
    ".html",
    ".iss",
    ".isl",
    ".js",
    ".json",
    ".md",
    ".props",
    ".ps1",
    ".py",
    ".rc",
    ".sh",
    ".targets",
    ".txt",
    ".typ",
    ".xml",
    ".yaml",
    ".yml",
}


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
        ROOT / "scripts" / "build_macos.sh",
        ROOT / "scripts" / "package_common.sh",
    )
    sources = "\n".join(path.read_text(encoding="utf-8") for path in script_paths)
    assert "tools/deps/" in sources
    assert "python311-" in sources
    assert "PROJECT_ROOT/python311" not in sources
    assert "grep -oP" not in sources

    macos_spec = (ROOT / "LaTeXSnipper-macos.spec").read_text(encoding="utf-8")
    assert "tools/deps/" not in macos_spec
    assert "BUNDLED_PY311" not in macos_spec
    assert "LATEXSNIPPER_BUNDLE_PYTHON_RUNTIME" not in macos_spec


def test_debian_control_template_is_dpkg_safe() -> None:
    control_bytes = (ROOT / "packaging" / "debian" / "DEBIAN" / "control").read_bytes()
    package_common = (ROOT / "scripts" / "package_common.sh").read_text(encoding="utf-8")

    assert not control_bytes.startswith(b"\xef\xbb\xbf")
    assert control_bytes.startswith(b"Package: latexsnipper\n")
    assert 'encoding="utf-8-sig"' in package_common


def test_text_sources_do_not_use_utf8_bom() -> None:
    offenders: list[str] = []
    ignored_parts = {"bin", "obj", "node_modules"}
    for root_name in BOM_CHECK_ROOTS:
        root = ROOT / root_name
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in BOM_CHECK_EXTENSIONS:
                continue
            if path.name.endswith(".user.props"):
                continue
            if ignored_parts.intersection(path.parts):
                continue
            if path.read_bytes().startswith(b"\xef\xbb\xbf"):
                offenders.append(path.relative_to(ROOT).as_posix())

    assert offenders == []


def test_macos_spec_bundles_collected_dependencies() -> None:
    macos_spec = (ROOT / "LaTeXSnipper-macos.spec").read_text(encoding="utf-8")
    macos_requirements = (ROOT / "requirements-macos.txt").read_text(encoding="utf-8")

    assert "coll = COLLECT(" in macos_spec
    assert "a.binaries" in macos_spec
    assert "a.datas" in macos_spec
    assert "app_bundle = BUNDLE(\n    coll," in macos_spec
    assert "app_bundle = BUNDLE(\n    exe," not in macos_spec
    assert "pynput" not in macos_spec
    assert "pynput" not in macos_requirements


def test_runtime_requirements_are_unified_and_windows_safe() -> None:
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    requirements = [line.strip() for line in requirements if line.strip() and not line.startswith("#")]
    assert requirements[:5] == [
        "PyQt6==6.10.0",
        "PyQt6-Qt6==6.10.0",
        "PyQt6-WebEngine==6.10.0",
        "PyQt6-WebEngine-Qt6==6.10.0",
        "PyQt6-Fluent-Widgets==1.11.2",
    ]
    assert "pywin32==311; sys_platform == \"win32\"" in requirements
    assert not any("linux" in spec.lower() for spec in requirements)

    build_requirements = (ROOT / "requirements-build.txt").read_text(encoding="utf-8")
    assert "pywin32==311" not in build_requirements
    assert "pypandoc==1.17" not in build_requirements
    assert "pypandoc>=1.15" not in build_requirements

    assert not (ROOT / "Inno" / "latexsnipper_offline.iss").exists()
    inno = (ROOT / "Inno" / "latexsnipper.iss").read_text(encoding="utf-8")
    assert r"DefaultDirName={localappdata}\{#MyAppName}" in inno
    assert "PrivilegesRequired=lowest" in inno
    assert "PrivilegesRequired=admin" not in inno
    assert r'MessagesFile: "{#MyRepoRoot}\Inno\ChineseSimplified.isl"' in inno
    assert (ROOT / "Inno" / "ChineseSimplified.isl").exists()
    assert "function ConfirmUninstallCleanup" in inno
    assert "InitializeUninstallProgressForm" not in inno
    assert "TSetupForm.Create" not in inno
    assert "CreateCustomForm(ScaleX(430), ScaleY(190), False, True)" in inno
    assert "{userprofile}" not in inno.lower()
    assert "{%USERPROFILE}" in inno
    assert "DeleteDependencyEnvsOnUninstall" in inno
    assert r'Type: filesandordirs; Name: "{app}\_internal"' in inno
    assert "已记录依赖根目录" in inno
    assert "安装目录下的依赖环境" not in inno
    assert "function ConfiguredDependencyRoot" in inno
    assert "JsonStringValue(String(ConfigText), 'install_base_dir')" in inno
    assert "procedure CleanupDependencyRootHistory" in inno
    assert "install_base_dir_cleanup_roots" in inno
    assert "procedure CleanupDependencyRootChildren" in inno
    assert "function IsPythonEnvironmentRoot" in inno
    assert "FileExists(AddBackslash(Path) + 'pyvenv.cfg')" in inno
    assert "FileExists(AddBackslash(Path) + 'Scripts\\python.exe')" in inno
    assert "CleanupPath(Root);" in inno
    assert "CleanupDependencyRootChildren(ExpandConstant('{app}'))" in inno
    assert "CleanupDependencyRootChildren(ConfiguredDependencyRoot())" in inno
    assert "CleanupDependencyRootHistory()" in inno
    assert inno.index("if DeleteDependencyEnvsOnUninstall then") < inno.index("if DeleteAppDataOnUninstall then")
    assert "CleanupPath(AddBackslash(Root) + 'pandoc')" in inno
    assert "CleanupPath(AddBackslash(Root) + 'translation_env')" in inno


def test_dependency_cleanup_is_documented_and_cross_platform() -> None:
    cleanup_script = (ROOT / "scripts" / "latexsnipper-clean-user-data.sh").read_text(encoding="utf-8")
    user_data_doc = (ROOT / "docs" / "user_data_storage.md").read_text(encoding="utf-8")
    faq_doc = (ROOT / "docs" / "faq.md").read_text(encoding="utf-8")
    manual_doc = (ROOT / "user_manual" / "user_manual.md").read_text(encoding="utf-8")
    manual_typ = (ROOT / "user_manual" / "user_manual.typ").read_text(encoding="utf-8")
    audit_doc = (ROOT / "docs" / "platform_adaptation_audit.md").read_text(encoding="utf-8")

    assert "--deps" in cleanup_script
    assert "install_base_dir" in cleanup_script
    assert "install_base_dir_cleanup_roots" in cleanup_script
    assert "argos_translation_env_dir" not in cleanup_script
    assert "pandoc" in cleanup_script
    assert "translation_env" in cleanup_script
    assert "is_python_environment_root()" in cleanup_script
    assert 'remove_path "$root" "dependency environment root"' in cleanup_script
    assert "rm -rf \"$root\"" not in cleanup_script
    assert "`<dependency-root>/pandoc`" in user_data_doc
    assert "`<dependency-root>/translation_env`" in user_data_doc
    assert "Direct child of the selected dependency root" in user_data_doc
    assert "Pandoc and Argos translation are not fixed to the application install" in user_data_doc
    assert "cleanup treats that recorded root as the environment and removes the whole root" in user_data_doc
    assert "`pandoc` for the optional dependency-managed Pandoc binary" in faq_doc
    assert "`translation_env` for the optional Argos local translation environment" in faq_doc
    assert "following the same active dependency root as Pandoc" in faq_doc
    assert "<依赖根>/pandoc" in manual_doc
    assert "<依赖根>/translation_env" in manual_doc
    assert "Windows:  <安装目录>\\_internal\\deps（默认，可在依赖向导/设置中切换）" in manual_doc
    assert "<依赖根>/pandoc" in manual_typ
    assert "<依赖根>/translation_env" in manual_typ
    assert "Windows:  <安装目录>\\_internal\\deps（默认，可在依赖向导/设置中切换）" in manual_typ
    assert "install-directory dependency environment" not in audit_doc
    assert "prompts before uninstall starts" in audit_doc


def test_release_workflow_pins_setuptools_before_bundled_seed_verification() -> None:
    release_workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    assert '"setuptools<82"' in release_workflow
    assert "pip install --upgrade pip wheel setuptools" not in release_workflow


def test_dependency_wizard_keeps_ui_status_icons_for_visible_labels() -> None:
    deps_ui = (ROOT / "src" / "bootstrap" / "deps_ui.py").read_text(encoding="utf-8")
    deps_layer_specs = (ROOT / "src" / "bootstrap" / "deps_layer_specs.py").read_text(encoding="utf-8")

    assert "✅ MATHCRAFT_GPU 已安装" in deps_ui
    assert "⚠️ MATHCRAFT_GPU 验证失败" in deps_ui
    assert "[OK] MATHCRAFT_GPU 已安装" not in deps_ui
    assert "[WARN] MATHCRAFT_GPU 验证失败" not in deps_ui
    assert '"[WARN] 该目录尚未检测到可复用的 Python 环境' not in deps_ui
    assert '"[WARN] 重要提示' not in deps_ui
    assert '"[LOCK]' not in deps_layer_specs
    assert '"[WARN] 依赖版本冲突' not in deps_layer_specs
    assert '"[NET]' not in deps_layer_specs


def test_workbench_disables_compute_engine_time_limit_after_cas_removal() -> None:
    app_js = (ROOT / "src" / "assets" / "mathlive" / "app.js").read_text(encoding="utf-8")

    assert "ce.timeLimit = 0;" in app_js
    assert "前端计算超时，已超过当前时限" not in app_js
    assert "前端计算引擎无法完成当前表达式" in app_js


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


def test_shutdown_cleans_office_bridge_toggle_workers() -> None:
    lifecycle = (ROOT / "src" / "ui" / "app_lifecycle_controller.py").read_text(encoding="utf-8")
    office_bridge = (ROOT / "src" / "ui" / "office_bridge_controller.py").read_text(encoding="utf-8")

    assert "def _cleanup_office_bridge_workers" in office_bridge
    assert "worker.completed.disconnect(receiver.handle_completed)" in office_bridge
    assert "worker.wait(timeout_ms)" in office_bridge
    assert "result_server.stop()" in office_bridge
    assert "self._office_bridge_toggle_workers.clear()" in office_bridge
    assert "self._cleanup_office_bridge_workers()" in lifecycle


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

    assert "function Stage-BundledPythonSeed" in script
    assert 'Join-Path $Root "build\\github-release"' in script
    assert 'Join-Path $stagingBase "bundled-deps"' in script
    assert 'Copy-Item -LiteralPath $source -Destination (Join-Path $stagedRoot "python311")' in script
    assert "function Normalize-BundledPythonSeed" in script
    assert 'Remove-Item -LiteralPath $pyvenvCfg -Force' in script
    assert "python311._pth" in script
    assert "Lib\\site-packages" in script
    assert '"Lib\\ensurepip"' in script
    assert '"Lib\\idlelib"' in script
    assert '"DLLs\\_tkinter.pyd"' in script
    assert '"include"' in script
    assert '"libs"' in script
    assert "$verifyCode = @'" in script
    assert '$verifyCode = @"' not in script
    assert "latexsnipper_verify_python_seed_" in script
    assert "& $pythonExe $verifyScript $seedRoot" in script
    assert "& $pythonExe -c $verifyCode $seedRoot" not in script
    assert 'for mod in ("pip", "setuptools", "wheel", "packaging")' not in script
    assert "sys.prefix does not point to bundled python311" in script
    assert "sys.path contains paths outside bundled python311" in script
    assert "Normalize-BundledPythonSeed -Root $bundledDepsRoot" in script
    assert "$env:LATEXSNIPPER_BUNDLED_DEPS_DIR = $bundledDepsRoot" in script
    assert "Normalize-BundledPythonSeed -Root $root" not in script
    assert "LaTeXSnipperSetup-2.4.0.exe" not in script
    assert 'Get-ChildItem -LiteralPath $installerOutputDir -Filter "LaTeXSnipperSetup-*.exe" -File' in script


def test_pyinstaller_specs_prune_bundled_python_seed_payload() -> None:
    for spec_name in ("LaTeXSnipper.spec", "LaTeXSnipper-linux.spec", "LaTeXSnipper-macos.spec"):
        spec = (ROOT / spec_name).read_text(encoding="utf-8")
        assert "_prune_bundled_python_runtime" in spec
        assert '"Lib/ensurepip"' in spec
        assert '"Lib/idlelib"' in spec
        assert '"DLLs/_tkinter.pyd"' in spec
        assert '"include"' in spec
        assert '"libs"' in spec


def test_windows_version_resource_matches_release_version() -> None:
    version_info = (ROOT / "version_info.txt").read_text(encoding="utf-8")
    file_version = re.search(r"StringStruct\('FileVersion', '([^']+)'\)", version_info)
    product_version = re.search(r"StringStruct\('ProductVersion', '([^']+)'\)", version_info)
    filevers = re.search(r"filevers=\((\d+),\s*(\d+),\s*(\d+),\s*(\d+)\)", version_info)
    prodvers = re.search(r"prodvers=\((\d+),\s*(\d+),\s*(\d+),\s*(\d+)\)", version_info)

    assert file_version is not None
    assert product_version is not None
    assert filevers is not None
    assert prodvers is not None
    expected = tuple(int(part) for part in file_version.group(1).split(".")) + (0,)
    assert product_version.group(1) == file_version.group(1)
    assert tuple(int(part) for part in filevers.groups()) == expected
    assert tuple(int(part) for part in prodvers.groups()) == expected
