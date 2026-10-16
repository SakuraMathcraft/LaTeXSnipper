"""Construct package-manager payloads exclusively from verified component files."""

from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess
import tempfile

from runtime.distribution_manifest import Component, ManifestError
from runtime.installation_layout import linux_prefix
from runtime.processes import independent_process_environment


def package_name(component: Component) -> str:
    return f'latexsnipper-{component.name}'


def build_package(source: Path, component: Component, output: Path) -> None:
    """No dependency resolution or network is involved in packaging the payload."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='debian-component-', dir=output.parent) as temporary:
        directory = Path(temporary)
        payload = directory / 'usr/lib/latexsnipper' / component.name
        payload.parent.mkdir(parents=True)
        if source.is_symlink():
            raise ManifestError('Package components cannot redirect outside their installation')
        if source.is_dir():
            def link_or_copy(original, destination):
                try:
                    os.link(original, destination)
                except OSError:
                    shutil.copy2(original, destination)
                return destination

            shutil.copytree(source, payload, symlinks=True, copy_function=link_or_copy)
        control = directory / 'DEBIAN'
        control.mkdir()
        architecture = {'x86_64': 'amd64', 'arm64': 'arm64', 'any': 'all'}[component.architecture]
        (control / 'control').write_text(
            f'Package: {package_name(component)}\nVersion: 0+{component.content_sha256}\n'
            f'Architecture: {architecture}\nMaintainer: MathCraft\nSection: utils\nPriority: optional\n'
            'Depends: latexsnipper\n'
            f'Description: LaTeXSnipper {component.name} resource component\n', encoding='utf-8',
        )
        result = subprocess.run(['dpkg-deb', '--root-owner-group', '--build', str(directory), str(output)],
                                capture_output=True, text=True, timeout=900, env=independent_process_environment())
        if result.returncode:
            raise ManifestError(f'Component package assembly failed: {result.stderr}')


def install_packages(root: Path, packages: list[Path]) -> None:
    if not packages:
        return
    prefix = linux_prefix(root)
    arguments = ['dpkg']
    if prefix != Path('/'):
        arguments += ['--root', str(prefix)]
    result = subprocess.run([*arguments, '--install', *map(str, packages)],
                            capture_output=True, text=True, timeout=900, env=independent_process_environment())
    if result.returncode:
        raise ManifestError(f'Component package installation failed: {result.stdout}\n{result.stderr}')


def purge_packages(root: Path, names: list[str]) -> None:
    if not names:
        return
    prefix = linux_prefix(root)
    arguments = ['dpkg']
    if prefix != Path('/'):
        arguments += ['--root', str(prefix)]
    result = subprocess.run([*arguments, '--purge', *[f'latexsnipper-{name}' for name in names]],
                            capture_output=True, text=True, timeout=900, env=independent_process_environment())
    if result.returncode:
        raise ManifestError(f'Incomplete first-install package cleanup failed: {result.stderr}')


def remove_packages(root: Path, names: list[str]) -> None:
    if not names:
        return
    prefix = linux_prefix(root)
    arguments = ['dpkg']
    if prefix != Path('/'):
        arguments += ['--root', str(prefix)]
    result = subprocess.run([*arguments, '--remove', *[f'latexsnipper-{name}' for name in names]],
                            capture_output=True, text=True, timeout=900, env=independent_process_environment())
    if result.returncode:
        raise ManifestError(f'Component package replacement could not begin: {result.stderr}')
