"""Native first-install carriers assembled only on GitHub Actions runners."""

from pathlib import Path
import os
import shutil
import subprocess
import tarfile

from runtime.distribution_manifest import DistributionManifest, ManifestError

ROOT = Path(__file__).resolve().parents[1]


def run(arguments, **kwargs) -> None:
    subprocess.run(list(map(str, arguments)), check=True, **kwargs)


def link_or_copy(source, destination):
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)
    return destination


def windows_installer(layout: Path, output: Path, manifest: DistributionManifest) -> Path:
    compiler = shutil.which('ISCC.exe')
    if compiler is None:
        raise ManifestError('Inno Setup compiler is required on the Windows release runner')
    run([compiler, f'/DMyBuildDir={layout}', f'/DMyOutputDir={output}', f'/DMyEdition={manifest.edition}', ROOT / 'Inno/latexsnipper.iss'])
    return output / f'LaTeXSnipper_{manifest.version}_windows_x86_64_{manifest.edition}.exe'


def linux_installer(layout: Path, output: Path, manifest: DistributionManifest) -> Path:
    carrier = layout.parent / f'linux-installer-{manifest.edition}'
    carrier.mkdir()
    payload = carrier / 'payload'
    shutil.copytree(layout, payload, symlinks=True, copy_function=link_or_copy)
    script = carrier / 'install.sh'
    script.write_text('''#!/bin/sh
set -eu
directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ "$(id -u)" != 0 ]; then
    exec sudo -- "$0" "$@"
fi
"$directory/payload/application/updater" --install-from "$directory/payload" --root /usr/lib/latexsnipper
printf 'Installed LaTeXSnipper. Start it from your application menu.\\n'
''', encoding='utf-8')
    script.chmod(0o755)
    path = output / f'LaTeXSnipper_{manifest.version}_linux_x86_64_{manifest.edition}.tar.gz'
    with tarfile.open(path, 'w:gz') as archive:
        archive.add(carrier, arcname='LaTeXSnipper')
    return path


def macos_installer(bundle: Path, output: Path, manifest: DistributionManifest) -> Path:
    staging = bundle.parent / 'dmg'
    staging.mkdir()
    run(['ditto', bundle, staging / bundle.name])
    (staging / 'Applications').symlink_to('/Applications', target_is_directory=True)
    path = output / f'LaTeXSnipper_{manifest.version}_macos_arm64_cpu.dmg'
    run(['hdiutil', 'create', '-volname', f'LaTeXSnipper {manifest.version}', '-srcfolder', staging,
         '-ov', '-format', 'UDZO', path])
    return path
