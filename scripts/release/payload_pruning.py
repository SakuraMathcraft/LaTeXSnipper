"""Prune only the staged standalone inference environment."""

import csv
from pathlib import Path

from payload_paths import remove_owned


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
            "__phello__",
            "__hello__.py",
            "lib2to3",
            "pydoc_data",
            "distutils",
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
    remove_owned(root / "share/terminfo", root)
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
        for name in ("distutils", "f2py", "_pyinstaller"):
            remove_owned(site / "numpy" / name, root)
        for name in ("backend", "datasets", "quantization", "tools", "transformers"):
            remove_owned(site / "onnxruntime" / name, root)
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
