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
    base = carrier / 'base'
    shutil.copytree(ROOT / 'packaging/debian', base)
    control = base / 'DEBIAN/control'
    text = control.read_text(encoding='utf-8').replace('Version: 0.0.0', f'Version: {manifest.version}')
    control.write_text(text, encoding='utf-8')
    directory = base / 'usr/lib/latexsnipper'
    directory.mkdir(parents=True, exist_ok=True)
    entry = directory / 'LaTeXSnipper'
    entry.write_text('''#!/bin/sh
set -eu
root=/usr/lib/latexsnipper
if [ -f "$root/.deployment/updater" ]; then
    exec "$root/.deployment/updater" --recover-root "$root"
fi
exec "$root/application/bootstrap/LaTeXSnipper" --installation-root "$root" "$@"
''', encoding='utf-8')
    entry.chmod(0o755)
    launcher = base / 'usr/bin/latexsnipper'
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text('#!/bin/sh\nexec /usr/lib/latexsnipper/LaTeXSnipper "$@"\n', encoding='utf-8')
    launcher.chmod(0o755)
    desktop = base / 'usr/share/applications/latexsnipper.desktop'
    desktop.parent.mkdir(parents=True, exist_ok=True)
    desktop.write_text('[Desktop Entry]\nType=Application\nName=LaTeXSnipper\nExec=latexsnipper\nIcon=latexsnipper\nCategories=Education;Science;\nTerminal=false\n', encoding='utf-8')
    shutil.copy2(ROOT / 'scripts/latexsnipper-clean-user-data.sh', base / 'usr/bin/latexsnipper-clean-user-data')
    (base / 'usr/bin/latexsnipper-clean-user-data').chmod(0o755)
    from PIL import Image

    icon = Image.open(ROOT / 'src/assets/icon.ico').convert('RGBA')
    for size in (16, 24, 32, 48, 64, 128, 256):
        destination = base / f'usr/share/icons/hicolor/{size}x{size}/apps/latexsnipper.png'
        destination.parent.mkdir(parents=True, exist_ok=True)
        icon.resize((size, size), Image.Resampling.LANCZOS).save(destination)
    for script in (base / 'DEBIAN').iterdir():
        if script.name != 'control':
            script.chmod(0o755)
    run(['dpkg-deb', '--root-owner-group', '--build', base, carrier / 'latexsnipper.deb'])
    shutil.rmtree(base)
    script = carrier / 'install.sh'
    script.write_text('''#!/bin/sh
set -eu
directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ "$(id -u)" != 0 ]; then
    exec sudo -- "$0" "$@"
fi
apt-get install -y --no-install-recommends "$directory/latexsnipper.deb"
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
    run(['codesign', '--timestamp', '--sign', os.environ['CODESIGN_IDENTITY'], path])
    return path
