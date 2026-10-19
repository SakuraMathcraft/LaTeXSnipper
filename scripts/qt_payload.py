"""Prune unused Qt modules and resources in the fixed GUI host."""

from pathlib import Path

from payload_paths import remove_owned

QT_OPTIONAL_MODULES = (
    "Qt6Multimedia",
    "Qt6MultimediaQuick",
    "Qt6Pdf",
    "Qt6PdfQuick",
    "Qt6Quick3D",
    "Qt6Quick3DAssetImport",
    "Qt6Quick3DAssetUtils",
    "Qt6Quick3DEffects",
    "Qt6Quick3DHelpers",
    "Qt6Quick3DHelpersImpl",
    "Qt6Quick3DParticles",
    "Qt6Quick3DPhysics",
    "Qt6Quick3DPhysicsHelpers",
    "Qt6Quick3DRuntimeRender",
    "Qt6Quick3DSpatialAudio",
    "Qt6Quick3DUtils",
    "Qt6Quick3DXr",
    "Qt6QuickControls2Imagine",
    "Qt6QuickControls2ImagineStyleImpl",
    "Qt6QuickControls2Material",
    "Qt6QuickControls2MaterialStyleImpl",
    "Qt6QuickControls2Universal",
    "Qt6QuickControls2UniversalStyleImpl",
    "Qt6QuickTest",
    "Qt6RemoteObjects",
    "Qt6RemoteObjectsQml",
    "Qt6Sensors",
    "Qt6SensorsQuick",
    "Qt6SerialPort",
    "Qt6SpatialAudio",
    "Qt6StateMachine",
    "Qt6StateMachineQml",
    "Qt6Test",
    "Qt6TextToSpeech",
    "Qt6WebEngineQuick",
    "Qt6WebEngineQuickDelegatesQml",
    "Qt6WebSockets",
)

QT_OPTIONAL_PLUGINS = (
    "generic/qtuiotouchplugin.dll",
    "imageformats/qicns.dll",
    "imageformats/qpdf.dll",
    "imageformats/qtga.dll",
    "imageformats/qwbmp.dll",
    "platforms/qminimal.dll",
    "position/qtposition_nmea.dll",
    "position/qtposition_positionpoll.dll",
    "position/qtposition_winrt.dll",
)


def prune_qt_payload(dist_root: Path) -> None:
    """Apply the same optional-module policy to DLL, ELF and framework layouts."""
    for name in ("Pythonwin", "_tcl_data", "_tk_data", "tcl8"):
        remove_owned(dist_root / name, dist_root)
    for pattern in (
        "_tkinter*.pyd",
        "_tkinter*.so",
        "tcl*.dll",
        "tk*.dll",
        "libtcl*.so*",
        "libtk*.so*",
        "_test*.pyd",
        "*_test.pyd",
        "_test*.so",
        "*_test.so",
    ):
        for path in dist_root.glob(pattern):
            remove_owned(path, dist_root)
    links = [
        (path, path.resolve())
        for path in dist_root.rglob("*")
        if path.is_symlink() and path.exists()
    ]
    for qt_root in (dist_root / "PyQt6/Qt6", dist_root / "Qt6"):
        if not qt_root.is_dir():
            continue
        resources = qt_root / "resources"
        remove_owned(resources / "qtwebengine_devtools_resources.pak", dist_root)
        for pattern in ("*.debug.pak", "*.debug.bin"):
            for path in resources.glob(pattern):
                remove_owned(path, dist_root)
        remove_owned(qt_root / "qml", dist_root)
        translations = qt_root / "translations"
        if translations.is_dir():
            for path in translations.iterdir():
                if path.name == "qtwebengine_locales":
                    continue
                if (
                    path.is_file()
                    and path.suffix == ".qm"
                    and any(
                        marker in path.stem for marker in ("_zh_CN", "_zh_TW", "_en")
                    )
                ):
                    continue
                remove_owned(path, dist_root)
        for path in (translations / "qtwebengine_locales").glob("*.pak"):
            if path.name not in {"en-US.pak", "zh-CN.pak"}:
                remove_owned(path, dist_root)
        # Shared libraries live in lib/ on Linux and macOS, independently of bin/.
        for directory in (qt_root / "bin", qt_root / "lib"):
            for stem in QT_OPTIONAL_MODULES:
                for alias in (stem, "Qt" + stem[3:]):
                    candidates = [
                        directory / f"{alias}.dll",
                        directory / f"lib{alias}.so",
                        directory / f"lib{alias}.dylib",
                        directory / f"{alias}.dylib",
                        directory / f"{alias}.framework",
                        *directory.glob(f"lib{alias}.so.*"),
                    ]
                    for path in candidates:
                        remove_owned(path, dist_root)
        for relative in QT_OPTIONAL_PLUGINS:
            plugin = Path(relative)
            directory = qt_root / "plugins" / plugin.parent
            for name in (
                f"{plugin.stem}.dll",
                f"lib{plugin.stem}.so",
                f"lib{plugin.stem}.dylib",
                f"{plugin.stem}.dylib",
            ):
                remove_owned(directory / name, dist_root)
    for path, target in links:
        if path.is_symlink() and not target.exists():
            remove_owned(path, dist_root)
