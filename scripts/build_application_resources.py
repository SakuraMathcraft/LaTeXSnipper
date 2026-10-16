"""Add owned worker source and locked Pandoc to a staged application component."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts'), str(ROOT / 'src')]

from build_desktop_resources import assemble_pandoc
from distribution_inputs import load_resources
from runtime.distribution_manifest import ManifestError


def assemble(args: argparse.Namespace) -> None:
    lock = load_resources(args.lock)
    application = args.application.resolve(strict=True)
    if not application.is_dir() or any((application / name).exists() for name in ('worker', 'pandoc')):
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--application', type=Path, required=True)
    parser.add_argument('--target', choices=('windows-x86_64', 'linux-x86_64', 'macos-arm64'), required=True)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--lock', type=Path, default=ROOT / 'packaging/runtime/resources.lock.json')
    assemble(parser.parse_args())


if __name__ == '__main__':
    main()
