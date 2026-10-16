"""Add owned worker source and locked Pandoc to a staged application component."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts'), str(ROOT / 'src')]

from build_desktop_resources import assemble_pandoc  # noqa: E402
from distribution_inputs import load_resources  # noqa: E402
from runtime.distribution_manifest import ManifestError  # noqa: E402


def assemble_linux_integration(directory: Path) -> None:
    """Ship package metadata and desktop integration inside the application identity."""
    from PIL import Image

    shutil.copytree(ROOT / 'packaging/debian', directory)
    entry = directory / 'usr/lib/latexsnipper/LaTeXSnipper'
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text('\n'.join((
        '#!/bin/sh', 'set -eu', 'root=/usr/lib/latexsnipper',
        'if [ -x "$root/application/bootstrap/LaTeXSnipper" ]; then',
        '    exec "$root/application/bootstrap/LaTeXSnipper" --installation-root "$root" "$@"',
        'fi', 'exec "$root/.deployment/updater" --recover-root "$root"', '',
    )), encoding='utf-8')
    entry.chmod(0o755)
    launcher = directory / 'usr/bin/latexsnipper'
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text('#!/bin/sh\nexec /usr/lib/latexsnipper/LaTeXSnipper "$@"\n', encoding='utf-8')
    launcher.chmod(0o755)
    desktop = directory / 'usr/share/applications/latexsnipper.desktop'
    desktop.parent.mkdir(parents=True, exist_ok=True)
    desktop.write_text('[Desktop Entry]\nType=Application\nName=LaTeXSnipper\nExec=latexsnipper\nIcon=latexsnipper\nCategories=Education;Science;\nTerminal=false\n', encoding='utf-8')
    shutil.copy2(ROOT / 'scripts/latexsnipper-clean-user-data.sh', directory / 'usr/bin/latexsnipper-clean-user-data')
    (directory / 'usr/bin/latexsnipper-clean-user-data').chmod(0o755)
    with Image.open(ROOT / 'src/assets/icon.ico') as icon:
        for size in (16, 24, 32, 48, 64, 128, 256):
            destination = directory / f'usr/share/icons/hicolor/{size}x{size}/apps/latexsnipper.png'
            destination.parent.mkdir(parents=True, exist_ok=True)
            icon.convert('RGBA').resize((size, size), Image.Resampling.LANCZOS).save(destination)
    for script in (directory / 'DEBIAN').iterdir():
        if script.name != 'control':
            script.chmod(0o755)


def assemble(args: argparse.Namespace) -> None:
    lock = load_resources(args.lock)
    application = args.application.resolve(strict=True)
    if not application.is_dir() or any((application / name).exists() for name in ('worker', 'pandoc', 'linux-integration')):
        raise ManifestError('Application resources require a staged app without existing worker or Pandoc')
    with tempfile.TemporaryDirectory(prefix='application-resources-', dir=application.parent) as temporary:
        staged = Path(temporary)
        package = staged / 'worker/mathcraft_ocr'
        package.mkdir(parents=True)
        for source in (ROOT / 'mathcraft_ocr').rglob('*'):
            if source.is_file() and source.suffix == '.py' and '__pycache__' not in source.parts:
                target = package / source.relative_to(ROOT / 'mathcraft_ocr')
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        shutil.copy2(ROOT / 'LICENSE', staged / 'worker/LICENSE')
        assemble_pandoc(lock, args.target, staged / 'pandoc', args.cache)
        (staged / 'worker').rename(application / 'worker')
        (staged / 'pandoc').rename(application / 'pandoc')
        if args.target.startswith('linux-'):
            assemble_linux_integration(application / 'linux-integration')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--application', type=Path, required=True)
    parser.add_argument('--target', choices=('windows-x86_64', 'linux-x86_64', 'macos-arm64'), required=True)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--lock', type=Path, default=ROOT / 'packaging/runtime/resources.lock.json')
    assemble(parser.parse_args())


if __name__ == '__main__':
    main()
