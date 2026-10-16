"""Recover Linux component updates through dpkg, including its ownership database."""

from __future__ import annotations

from pathlib import Path
import shutil

from runtime.component_inventory import verify_component
from runtime.distribution_manifest import DistributionManifest, ManifestError
from runtime.installation_layout import installation_manifest
from update.component_plan import plan_component_update
from update.debian_packages import build_package, install_packages, purge_packages, remove_packages
from update.deployment_transaction import DeploymentTransaction, atomic_json, verify_distribution, verify_distribution_sources


class DebianDeploymentTransaction(DeploymentTransaction):
    def __init__(self, root: Path):
        super().__init__(root)
        self.metadata = installation_manifest(self.root, 'linux')

    def _rollback(self, state: dict) -> None:
        self._save(state, 'rolling-back')
        packages = [self.directory / 'backup' / f'{name}.deb' for name in state['replacements']]
        if state['before'] is None:
            purge_packages(self.root, state['replacements'])
        else:
            install_packages(self.root, packages)
        if state['before'] is None:
            self.metadata.unlink(missing_ok=True)
        else:
            atomic_json(self.metadata, state['before'])
        self._save(state, 'rolled-back')

    def apply(self, staged: Path, *, validate=verify_distribution, checkpoint=None, complete: bool = False) -> DistributionManifest:
        staged = staged.resolve(strict=True)
        if staged.is_relative_to(self.root) or self.root.is_relative_to(staged):
            raise ManifestError('Staging must be separate from the installation')
        with self._lock():
            self._recover()
            before = DistributionManifest.load(self.metadata) if self.metadata.is_file() else None
            target = DistributionManifest.load(staged / 'distribution.json')
            if complete:
                if before is not None and before.target[:2] != target.target[:2]:
                    raise ManifestError('Reinstallation cannot change platform or architecture')
                if before is None and any((self.root / item.name).exists() for item in target.components):
                    raise ManifestError('Cannot initialize unmanaged component directories')
                replacements = target.components
            else:
                if before is None:
                    raise ManifestError('Updating requires an existing installation identity')
                damaged = [item.name for item in before.components if verify_component(self.root / item.name, item)]
                replacements = plan_component_update(before, target, damaged_components=damaged).downloads
            names = [item.name for item in replacements]
            expected = {'distribution.json', *names}
            if complete and (staged / 'LaTeXSnipper').is_file():
                expected.add('LaTeXSnipper')
            if {item.name for item in staged.iterdir()} != expected:
                raise ManifestError('Staging contains unexpected resources')
            verify_distribution_sources(self.root, staged, target, names)
            incoming_bytes = sum(record.size for component in replacements for record in component.files)
            backup_bytes = sum(record.size for name in names for record in before.component(name).files) if before else 0
            required = max(incoming_bytes * 2, incoming_bytes + backup_bytes) + 8 * 1024 * 1024
            if shutil.disk_usage(self.root).free < required:
                raise OSError('Insufficient space for component packages and failure recovery')
            self.directory.mkdir()
            (self.directory / 'incoming').mkdir()
            (self.directory / 'backup').mkdir()
            for component in replacements:
                build_package(staged / component.name, component, self.directory / 'incoming' / f'{component.name}.deb')
                original = before.component(component.name) if before else component
                build_package(self.root / component.name, original, self.directory / 'backup' / f'{component.name}.deb')
            state = {'schema': 1, 'status': 'prepared', 'before': before.to_dict() if before else None, 'target': target.to_dict(), 'complete': complete,
                     'replacements': names, 'present': {name: (self.root / name).is_dir() for name in names}}
            self._save(state, 'prepared')
            try:
                if checkpoint:
                    checkpoint('prepared')
                self._save(state, 'applying')
                remove_packages(self.root, names)
                for name in names:
                    self._remove(self.root / name)
                install_packages(self.root, [self.directory / 'incoming' / f'{name}.deb' for name in names])
                if checkpoint:
                    checkpoint('packages-installed')
                self._save(state, 'validating')
                verify_distribution(self.root, target)
                validate(self.root, target)
                self.metadata.parent.mkdir(parents=True, exist_ok=True)
                atomic_json(self.metadata, target.installed_identity().to_dict())
                if checkpoint:
                    checkpoint('manifest-written')
                self._save(state, 'committed')
            except Exception:
                self._rollback(state)
                self._remove(self.directory)
                raise
            self._remove(self.directory)
            return target
