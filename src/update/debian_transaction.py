"""Recover Linux component updates through dpkg, including its ownership database."""

from __future__ import annotations

from pathlib import Path
import shutil

from runtime.installation_layout import installation_manifest
from update.debian_packages import build_package, install_packages, purge_packages
from update.deployment_transaction import DeploymentTransaction


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
        self._restore_identity(state)

    def _prepare(self, staged, before, target, replacements) -> dict:
        incoming_bytes = sum(record.size for component in replacements for record in component.files)
        backup_bytes = sum(record.size for component in replacements for record in before.component(component.name).files) if before else 0
        required = max(incoming_bytes * 2, incoming_bytes + backup_bytes) + 8 * 1024 * 1024
        if shutil.disk_usage(self.root).free < required:
            raise OSError('Insufficient space for component packages and failure recovery')
        (self.directory / 'incoming').mkdir()
        (self.directory / 'backup').mkdir()
        for component in replacements:
            build_package(staged / component.name, component, self.directory / 'incoming' / f'{component.name}.deb')
            if before is not None:
                previous = before.component(component.name)
                integration = None
                if component.name == 'application' and previous.content_sha256 == component.content_sha256:
                    # A same-content repair can rebuild package metadata from its
                    # verified payload even when the installed copy is damaged.
                    integration = staged / component.name / 'linux-integration'
                build_package(self.root / component.name, previous, self.directory / 'backup' / f'{component.name}.deb', integration=integration)
        return {}

    def _install(self, state, checkpoint):
        names = state['replacements']
        for name in names:
            self._remove(self.root / name)
        install_packages(self.root, [self.directory / 'incoming' / f'{name}.deb' for name in names], resolve_dependencies=True)
        if checkpoint:
            checkpoint('packages-installed')
