"""Platform ownership of installation metadata and component resource roots."""

from pathlib import Path

from runtime.distribution_manifest import ManifestError


def linux_prefix(root: Path) -> Path:
    root = root.resolve()
    if root.parts[-3:] != ('usr', 'lib', 'latexsnipper'):
        raise ManifestError('Linux components must use their package-owned usr/lib/latexsnipper layout')
    return root.parents[2]


def macos_bundle(root: Path) -> Path:
    root = root.resolve()
    if root.parts[-3:] != ('Contents', 'Resources', 'desktop') or root.parents[2].suffix != '.app':
        raise ManifestError('macOS components must belong to the desktop resource directory of an app bundle')
    return root.parents[2]


def installation_manifest(root: Path, system: str) -> Path:
    if system == 'linux':
        return linux_prefix(root) / 'var/lib/latexsnipper/distribution.json'
    return root / 'distribution.json'


def deployment_directory(root: Path, system: str) -> Path:
    if system == 'macos':
        bundle = macos_bundle(root)
        return bundle.parent / f'.{bundle.name}.deployment'
    return root / '.deployment'


def deployment_write_root(root: Path, system: str) -> Path:
    return macos_bundle(root).parent if system == 'macos' else root
