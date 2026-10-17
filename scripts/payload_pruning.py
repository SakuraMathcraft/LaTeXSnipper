"""Shared, staging-only pruning for desktop application and inference payloads."""

import csv
import shutil
from pathlib import Path


def remove_owned(path: Path, owner: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if not path.resolve().is_relative_to(owner.resolve()):
        raise ValueError("Payload cleanup escaped its staging directory")
    if path.is_symlink() or path.is_file():
        path.unlink()
    else:
        shutil.rmtree(path)


def prune_runtime_payload(root: Path) -> None:
    standard_libraries = [
        path
        for path in (root / "Lib", *(root / "lib").glob("python*"))
        if path.is_dir() and (path / "site-packages").is_dir()
    ]
    sites = [path / "site-packages" for path in standard_libraries]
    for standard in standard_libraries:
        # unittest stays: third-party imports can require unittest.mock.
        for name in (
            "idlelib",
            "tkinter",
            "turtledemo",
            "turtle.py",
            "ensurepip",
            "venv",
            "test",
        ):
            remove_owned(standard / name, root)
        for path in (standard / "lib-dynload").glob("_tkinter*"):
            remove_owned(path, root)
    for pattern in ("_tkinter*.pyd", "tcl*.dll", "tk*.dll"):
        for path in (root / "DLLs").glob(pattern):
            remove_owned(path, root)
    for pattern in ("libtcl*", "libtk*", "tcl8*", "tk8*"):
        for path in (root / "lib").glob(pattern):
            remove_owned(path, root)
    remove_owned(root / "pythonw.exe", root)
    for site in sites:
        for path in site.iterdir():
            if path.name in {
                "pip",
                "setuptools",
                "wheel",
                "pkg_resources",
                "_distutils_hack",
                "distutils-precedence.pth",
            } or path.name.startswith(("pip-", "setuptools-", "wheel-")):
                remove_owned(path, root)
    for scripts in (root / "Scripts", root / "bin"):
        if scripts.is_dir():
            for path in scripts.iterdir():
                if path.name not in {"python", "python3", "python3.11", "python.exe"}:
                    remove_owned(path, root)
    for name in ("include", "libs", "tcl", "Tools", "Doc"):
        remove_owned(root / name, root)
    for site in sites:
        # Image OCR uses neither Haar cascades nor OpenCV's GUI resources.
        for relative in ("cv2/qt", "cv2/samples"):
            remove_owned(site / relative, root)
        for path in (site / "cv2/data").glob("haarcascade*.xml"):
            remove_owned(path, root)
        # This optional video plugin is separate on Windows. Keep ELF/Mach-O
        # codec libraries, which can be direct dependencies of the cv2 extension.
        for path in (site / "cv2").glob("opencv_videoio_ffmpeg*.dll"):
            remove_owned(path, root)
        # Desktop GPU inference selects CUDA; it does not ship TensorRT.
        for path in (site / "onnxruntime/capi").glob("*providers_tensorrt*"):
            remove_owned(path, root)
        # OCR supplies its own model component; RapidOCR dictionaries stay in place.
        for path in (site / "rapidocr/models").glob("*.onnx"):
            remove_owned(path, root)
        for path in list(site.rglob("tests")):
            if path.is_dir():
                remove_owned(path, root)
        for extension in ("*.h", "*.hpp", "*.pxd", "*.pyi", "*.a", "*.lib", "*.o"):
            for path in list(site.rglob(extension)):
                remove_owned(path, root)
    for path in list(root.rglob("direct_url.json")):
        if path.parent.name.endswith(".dist-info"):
            remove_owned(path, root)
    for path in list(root.rglob("__pycache__")):
        remove_owned(path, root)
    for site in sites:
        for record in site.glob("*.dist-info/RECORD"):
            with record.open(encoding="utf-8", newline="") as stream:
                rows = list(csv.reader(stream))
            kept = [
                row
                for row in rows
                if row
                and (site / row[0]).resolve().is_relative_to(root.resolve())
                and (site / row[0]).is_file()
            ]
            with record.open("w", encoding="utf-8", newline="") as stream:
                csv.writer(stream).writerows(kept)


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
