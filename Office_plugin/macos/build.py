"""Build LaTeXSnipper Office.app and its DMG, separately from the desktop app.

    python Office_plugin/macos/build.py [--output DIR] [--work DIR]

Needs macOS, the Python in Office_plugin/macos/requirements.txt (including
PyInstaller) and Xcode command line tools. Nothing from the desktop app's
build is used; the add-in carries its own copy of the MathJax ``office``
resource profile, which the Windows installer also ships.
"""

from __future__ import annotations

import argparse
import json
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE / "host"))
APP_NAME = "LaTeXSnipper Office"
BUNDLE_ID = "com.mathcraft.latexsnipper.office"
MINIMUM_MACOS = "12.0"
_IGNORED = shutil.ignore_patterns(".DS_Store", "__pycache__", "*.pyc")


def version() -> str:
    return (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def assemble_resources(target: Path) -> Path:
    """Write the packaged layout read by ``latexsnipper_office.assets.packaged_assets``."""

    from latexsnipper_office.assets import source_assets

    source = source_assets(ROOT, ROOT / "src/assets/MathJax")
    addin = target / "office_addin"
    shutil.copytree(source.web, addin / "web", ignore=_IGNORED)
    shutil.copytree(source.shared_editor, addin / "shared", ignore=_IGNORED)
    shutil.copytree(source.support, addin / "support", ignore=_IGNORED)
    shutil.copy2(source.typography_adapter, addin / source.typography_adapter.name)
    shutil.copy2(source.manifest_template, addin / "manifest.xml")
    mathjax = ROOT / "src/assets/MathJax"
    profile = json.loads((mathjax / "resources.json").read_text(encoding="utf-8"))[
        "profiles"
    ]["office"]
    for relative in [
        *profile,
        "config.js",
        "runtime.js",
        "office.js",
        "resources.json",
    ]:
        destination = addin / "MathJax" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(mathjax / relative, destination)
    shutil.copy2(ROOT / "VERSION", target / "VERSION")
    return addin


def _run(*command: object, cwd: Path | None = None) -> None:
    subprocess.run([str(part) for part in command], check=True, cwd=cwd)


def icon(work: Path) -> Path:
    from PIL import Image

    iconset = work / "app.iconset"
    iconset.mkdir()
    image = Image.open(ROOT / "src/assets/icon.ico").convert("RGBA")
    for size in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            suffix = "@2x" if scale == 2 else ""
            image.resize((size * scale, size * scale), Image.Resampling.LANCZOS).save(
                iconset / f"icon_{size}x{size}{suffix}.png"
            )
    output = work / "app.icns"
    _run("iconutil", "-c", "icns", iconset, "-o", output)
    return output


def build_app(work: Path) -> Path:
    resources = work / "resources"
    assemble_resources(resources)
    datas = [f"{resources / 'office_addin'}:office_addin", f"{resources / 'VERSION'}:."]
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        APP_NAME,
        "--osx-bundle-identifier",
        BUNDLE_ID,
        "--icon",
        icon(work),
        "--distpath",
        work / "dist",
        "--workpath",
        work / "pyinstaller",
        "--specpath",
        work,
        "--paths",
        HERE / "host",
        "--collect-submodules",
        "latexsnipper_office",
        "--hidden-import",
        "CoreText",
        "--hidden-import",
        "Quartz",
        "--hidden-import",
        "AppKit",
        # The host is a small server: none of the desktop's GUI or OCR stack.
        "--exclude-module",
        "PyQt6",
        "--exclude-module",
        "tkinter",
        "--exclude-module",
        "numpy",
        "--exclude-module",
        "onnxruntime",
    ]
    for data in datas:
        command += ["--add-data", data]
    _run(*command, HERE / "host/latexsnipper_office/__main__.py")
    app = work / "dist" / f"{APP_NAME}.app"
    info = app / "Contents/Info.plist"
    with info.open("rb") as stream:
        plist = plistlib.load(stream)
    plist.update(
        {
            "CFBundleShortVersionString": version(),
            "CFBundleVersion": version(),
            "LSMinimumSystemVersion": MINIMUM_MACOS,
            "NSHumanReadableCopyright": "Copyright 2026 MathCraft",
            # Word formula metadata lives in document variables, which only
            # Word's AppleScript interface can write.
            "NSAppleEventsUsageDescription": "LaTeXSnipper Office 需要控制 Microsoft Word，以便在文档中保存公式数据。",
        }
    )
    with info.open("wb") as stream:
        plistlib.dump(plist, stream)
    for junk in app.rglob(".DS_Store"):
        junk.unlink()
    _run("codesign", "--force", "--deep", "--sign", "-", app)
    _run("codesign", "--verify", "--deep", "--strict", app)
    return app


def build_dmg(app: Path, output: Path) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    staging = app.parent.parent / "dmg"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir()
    _run("ditto", app, staging / app.name)
    (staging / "Applications").symlink_to("/Applications", target_is_directory=True)
    dmg = output / f"LaTeXSnipperOffice_{version()}_macos_arm64.dmg"
    _run(
        "hdiutil",
        "create",
        "-volname",
        f"{APP_NAME} {version()}",
        "-srcfolder",
        staging,
        "-ov",
        "-fs",
        "APFS",
        "-format",
        "UDZO",
        dmg,
    )
    return dmg


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--output", type=Path, default=HERE / "release")
    # Default outside the checkout: Finder writes .DS_Store into folders it shows.
    parser.add_argument("--work", type=Path)
    args = parser.parse_args()
    if sys.platform != "darwin":
        raise SystemExit("LaTeXSnipper Office for Mac must be built on macOS.")
    if args.work:
        shutil.rmtree(args.work, ignore_errors=True)
        args.work.mkdir(parents=True)
        work = args.work
    else:
        work = Path(tempfile.mkdtemp(prefix="latexsnipper-office-"))
    dmg = build_dmg(build_app(work), args.output.resolve())
    print(dmg)


if __name__ == "__main__":
    main()
