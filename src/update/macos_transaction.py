"""Reconstruct a sealed app and atomically exchange whole bundles on macOS."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
import shutil
import subprocess

from runtime.distribution_manifest import DistributionManifest, ManifestError
from runtime.component_inventory import verify_component
from runtime.installation_layout import deployment_directory, macos_bundle
from runtime.processes import independent_process_environment
from update.deployment_transaction import DeploymentTransaction, verify_distribution

DESKTOP = Path('Contents/Resources/desktop')


def verify_bundle(bundle: Path) -> None:
    arguments = ['codesign', '--verify', '--deep', '--strict', '--verbose=2', str(bundle)]
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=120, env=independent_process_environment())
    if result.returncode:
        raise ManifestError(f'macOS bundle signature validation failed: {result.stderr or result.stdout}')


def bundle_is_damaged(root: Path) -> bool:
    try:
        verify_bundle(macos_bundle(root))
        return False
    except (OSError, subprocess.SubprocessError, ManifestError):
        return True


def exchange_bundles(first: Path, second: Path) -> None:
    # Darwin's RENAME_SWAP (bsd/sys/stdio.h) is an atomic exchange. Filesystems
    # that cannot perform it fail before either bundle name is changed.
    library = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
    library.renamex_np.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
    library.renamex_np.restype = ctypes.c_int
    if library.renamex_np(os.fsencode(first), os.fsencode(second), 0x00000002):
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def overlay_bundle_seal(candidate: Path, seal: Path) -> None:
    """Replace only the outer signed resources; components remain independently owned."""
    if {item.name for item in seal.iterdir()} != {'Contents'} or not (seal / 'Contents/Info.plist').is_file():
        raise ManifestError('Bundle seal must contain one complete Contents resource tree')
    for component in ('application', 'inference', 'models'):
        if (seal / DESKTOP / component).exists():
            raise ManifestError('Bundle seal cannot contain component payloads')
    keep = {DESKTOP / name for name in ('application', 'inference', 'models')}
    for entry in sorted(candidate.rglob('*'), key=lambda path: len(path.parts), reverse=True):
        relative = entry.relative_to(candidate)
        if any(relative == directory or relative.is_relative_to(directory) for directory in keep):
            continue
        if entry.is_symlink() or entry.is_file():
            entry.unlink()
        elif entry.is_dir() and not any(entry.iterdir()):
            entry.rmdir()
    shutil.copytree(seal, candidate, dirs_exist_ok=True, symlinks=True)


class MacOSDeploymentTransaction(DeploymentTransaction):
    JOURNAL_FIELDS = DeploymentTransaction.JOURNAL_FIELDS | {'original_bundle'}

    def __init__(self, root: Path):
        super().__init__(root)
        self.bundle = macos_bundle(self.root)
        self.owner = self.bundle
        self.directory = deployment_directory(self.root, 'macos')
        if self.directory.is_symlink():
            raise ManifestError('Deployment state cannot redirect outside the bundle owner')
        self.journal = self.directory / 'journal.json'
        self.lockfile = self.directory.with_suffix('.lock')
        self.candidate = self.directory / self.bundle.name

    def _state(self) -> dict:
        state = super()._state()
        identity = state['original_bundle']
        if not isinstance(identity, list) or len(identity) != 2 or any(type(value) is not int for value in identity):
            raise ManifestError('Invalid original bundle identity')
        return state

    def _validate_installed(self, target: DistributionManifest) -> None:
        verify_distribution(self.root, target)
        verify_bundle(self.bundle)

    def _rollback(self, state: dict) -> None:
        self._save(state, 'rolling-back')
        original = state['original_bundle']
        current = self.bundle.stat()
        if [current.st_dev, current.st_ino] != original:
            previous = self.candidate.stat()
            if [previous.st_dev, previous.st_ino] != original:
                raise ManifestError('Original app bundle is unavailable for interrupted deployment recovery')
            exchange_bundles(self.bundle, self.candidate)
        self._save(state, 'rolled-back')

    def _prepare(self, staged, before, target, replacements) -> dict:
        required = sum(record.size for component in target.components for record in component.files)
        if shutil.disk_usage(self.bundle.parent).free < required:
            raise OSError('Insufficient space for a complete target app bundle')
        result = subprocess.run(['ditto', str(self.bundle), str(self.candidate)], capture_output=True, text=True, timeout=900, env=independent_process_environment())
        if result.returncode:
            raise ManifestError(f'App bundle preparation failed: {result.stderr}')
        candidate_root = self.candidate / DESKTOP
        for component in replacements:
            self._remove(candidate_root / component.name)
            shutil.copytree(staged / component.name, candidate_root / component.name, symlinks=True)
        if (staged / '.bundle-seal').is_dir():
            if target.bundle_seal is None or verify_component(staged / '.bundle-seal', target.bundle_seal):
                raise ManifestError('Prepared bundle seal does not match the authoritative inventory')
            overlay_bundle_seal(self.candidate, staged / '.bundle-seal')
        if DistributionManifest.load(candidate_root / 'distribution.json') != target.installed_identity():
            raise ManifestError('Signed bundle identity does not match the authoritative target')
        verify_distribution(candidate_root, target)
        verify_bundle(self.candidate)
        original = self.bundle.stat()
        return {'original_bundle': [original.st_dev, original.st_ino]}

    def _install(self, state, checkpoint):
        exchange_bundles(self.bundle, self.candidate)
        if checkpoint:
            checkpoint('bundle-exchanged')

    def _publish(self, state):
        # The verified bundle seal already contains its installed identity.
        if DistributionManifest.load(self.metadata) != DistributionManifest.from_dict(state['target']).installed_identity():
            raise ManifestError('Installed bundle identity changed before commit')
