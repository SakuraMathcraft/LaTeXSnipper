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
from update.component_plan import plan_component_update
from update.deployment_transaction import DeploymentTransaction, verify_distribution, verify_distribution_sources

DESKTOP = Path('Contents/Resources/desktop')


def verify_bundle(bundle: Path) -> None:
    for arguments in (
        ['codesign', '--verify', '--deep', '--strict', '--verbose=2', str(bundle)],
        ['xcrun', 'stapler', 'validate', str(bundle)],
        ['spctl', '--assess', '--type', 'execute', '--verbose=2', str(bundle)],
    ):
        result = subprocess.run(arguments, capture_output=True, text=True, timeout=120, env=independent_process_environment())
        if result.returncode:
            raise ManifestError(f'macOS bundle trust validation failed: {result.stderr or result.stdout}')


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

    def _verify_committed(self, target: DistributionManifest) -> None:
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

    def apply(self, staged: Path, *, validate=verify_distribution, checkpoint=None) -> DistributionManifest:
        staged = staged.resolve(strict=True)
        if staged.is_relative_to(self.bundle) or self.bundle.is_relative_to(staged):
            raise ManifestError('Staging must be separate from the installed app bundle')
        with self._lock():
            self._recover()
            before = DistributionManifest.load(self.metadata)
            target = DistributionManifest.load(staged / 'distribution.json')
            damaged = [item.name for item in before.components if verify_component(self.root / item.name, item)]
            plan = plan_component_update(before, target, damaged_components=damaged, damaged_bundle=bundle_is_damaged(self.root))
            names = [item.name for item in plan.downloads]
            expected = {'distribution.json', *names}
            if plan.seal_required:
                expected.add('.bundle-seal')
            if {item.name for item in staged.iterdir()} != expected:
                raise ManifestError('Staging contains unexpected bundle resources')
            verify_distribution_sources(self.root, staged, target, names)
            required = sum(record.size for component in target.components for record in component.files)
            if shutil.disk_usage(self.bundle.parent).free < required:
                raise OSError('Insufficient space for a complete target app bundle')
            self.directory.mkdir()
            result = subprocess.run(['ditto', str(self.bundle), str(self.candidate)], capture_output=True, text=True, timeout=900, env=independent_process_environment())
            if result.returncode:
                raise ManifestError(f'App bundle preparation failed: {result.stderr}')
            candidate_root = self.candidate / DESKTOP
            for name in names:
                self._remove(candidate_root / name)
                shutil.copytree(staged / name, candidate_root / name, symlinks=True)
            if plan.seal_required:
                if target.bundle_seal is None or verify_component(staged / '.bundle-seal', target.bundle_seal):
                    raise ManifestError('Prepared bundle seal does not match the authoritative inventory')
                overlay_bundle_seal(self.candidate, staged / '.bundle-seal')
            if DistributionManifest.load(candidate_root / 'distribution.json') != target.installed_identity():
                raise ManifestError('Signed bundle identity does not match the authoritative target')
            verify_distribution(candidate_root, target)
            verify_bundle(self.candidate)
            validate(candidate_root, target)
            original = self.bundle.stat()
            state = {'schema': 1, 'status': 'prepared', 'before': before.to_dict(), 'target': target.to_dict(), 'complete': False,
                     'replacements': names, 'present': {name: (self.root / name).is_dir() for name in names},
                     'original_bundle': [original.st_dev, original.st_ino]}
            self._save(state, 'prepared')
            try:
                if checkpoint:
                    checkpoint('prepared')
                self._save(state, 'applying')
                exchange_bundles(self.bundle, self.candidate)
                if checkpoint:
                    checkpoint('bundle-exchanged')
                self._save(state, 'validating')
                verify_bundle(self.bundle)
                verify_distribution(self.root, target)
                validate(self.root, target)
                self._save(state, 'committed')
                if checkpoint:
                    checkpoint('committed')
            except Exception:
                self._rollback(state)
                self._remove(self.directory)
                raise
            self._remove(self.directory)
            return target
