"""Assemble business bytecode, worker source and desktop integration."""

from __future__ import annotations

import argparse
import py_compile
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts"), str(ROOT / "src")]


def assemble_linux_integration(directory: Path) -> None:
    """Ship package metadata and desktop integration inside the application identity."""
    from PIL import Image

    shutil.copytree(ROOT / "packaging/debian", directory)
    entry = directory / "usr/lib/latexsnipper/LaTeXSnipper"
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text(
        "\n".join(
            (
                "#!/bin/sh",
                "set -eu",
                "root=/usr/lib/latexsnipper",
                'if [ -x "$root/application/bootstrap/LaTeXSnipper" ]; then',
                '    exec "$root/application/bootstrap/LaTeXSnipper" --installation-root "$root" "$@"',
                "fi",
                'exec "$root/.deployment/updater" --recover-root "$root"',
                "",
            )
        ),
        encoding="utf-8",
    )
    entry.chmod(0o755)
    launcher = directory / "usr/bin/latexsnipper"
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text(
        '#!/bin/sh\nexec /usr/lib/latexsnipper/LaTeXSnipper "$@"\n', encoding="utf-8"
    )
    launcher.chmod(0o755)
    desktop = directory / "usr/share/applications/latexsnipper.desktop"
    desktop.parent.mkdir(parents=True, exist_ok=True)
    desktop.write_text(
        "[Desktop Entry]\nType=Application\nName=LaTeXSnipper\nExec=latexsnipper\nIcon=latexsnipper\nCategories=Education;Science;\nTerminal=false\n",
        encoding="utf-8",
    )
    shutil.copy2(
        ROOT / "scripts/latexsnipper-clean-user-data.sh",
        directory / "usr/bin/latexsnipper-clean-user-data",
    )
    (directory / "usr/bin/latexsnipper-clean-user-data").chmod(0o755)
    with Image.open(ROOT / "src/assets/icon.ico") as icon:
        for size in (16, 24, 32, 48, 64, 128, 256):
            destination = (
                directory
                / f"usr/share/icons/hicolor/{size}x{size}/apps/latexsnipper.png"
            )
            destination.parent.mkdir(parents=True, exist_ok=True)
            icon.convert("RGBA").resize((size, size), Image.Resampling.LANCZOS).save(
                destination
            )
    for script in (directory / "DEBIAN").iterdir():
        if script.name != "control":
            script.chmod(0o755)


def assemble(args: argparse.Namespace) -> None:
    application = args.application.resolve()
    application.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="business-bytecode-") as temporary:
        compiled = Path(temporary) / "module.pyc"
        with zipfile.ZipFile(application / "application.pyz", "w") as archive:
            for source in sorted((ROOT / "src").rglob("*")):
                relative = source.relative_to(ROOT / "src")
                if (
                    not source.is_file()
                    or "__pycache__" in relative.parts
                    or "MathJax" in relative.parts
                    or source.suffix in {".pyc", ".pyo"}
                ):
                    continue
                if source.suffix == ".py":
                    py_compile.compile(
                        str(source),
                        cfile=str(compiled),
                        dfile=relative.as_posix(),
                        doraise=True,
                        invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH,
                    )
                    entry = zipfile.ZipInfo(relative.with_suffix(".pyc").as_posix())
                    archive.writestr(
                        entry,
                        compiled.read_bytes(),
                        compress_type=zipfile.ZIP_DEFLATED,
                        compresslevel=6,
                    )
                else:
                    destination = application / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
    package = application / "worker/mathcraft_ocr"
    shutil.copytree(
        ROOT / "mathcraft_ocr",
        package,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", "*.onnx"),
    )
    shutil.copy2(ROOT / "LICENSE", application / "LICENSE")
    if args.target.startswith("linux-"):
        assemble_linux_integration(application / "linux-integration")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--application", type=Path, required=True)
    parser.add_argument(
        "--target",
        choices=("windows-x86_64", "linux-x86_64", "macos-arm64"),
        required=True,
    )
    assemble(parser.parse_args())


if __name__ == "__main__":
    main()
