"""Recover Linux component updates through dpkg, including its ownership database."""

from __future__ import annotations

import shutil
from pathlib import Path

from runtime.installation_layout import installation_manifest
from update.debian_packages import build_package, install_packages, purge_packages
from update.deployment_transaction import DeploymentTransaction


class DebianDeploymentTransaction(DeploymentTransaction):
    def __init__(self, root: Path):
        super().__init__(root)
        self.metadata = installation_manifest(self.root, "linux")

    def _rollback(self, state: dict) -> None:
        self._save(state, "rolling-back")
        original = [name for name in state["replacements"] if state["present"][name]]
        missing = [name for name in state["replacements"] if not state["present"][name]]
        purge_packages(self.root, missing)
        install_packages(
            self.root, [self.directory / "backup" / f"{name}.deb" for name in original]
        )
        self._restore_identity(state)

    def _prepare(self, staged, before, target, replacements) -> dict:
        required = (
            sum(
                path.stat().st_size
                for name in replacements
                for path in (staged / name).rglob("*")
                if path.is_file()
            )
            * 3
        )
        if shutil.disk_usage(self.root).free < required:
            raise OSError("Insufficient space for packages and failure recovery")
        (self.directory / "incoming").mkdir()
        (self.directory / "backup").mkdir()
        for name in replacements:
            identity = (
                target.application.content_sha256
                if name == "application"
                else target.base_id
            )
            build_package(
                staged / name,
                name,
                identity,
                self.directory / "incoming" / f"{name}.deb",
            )
            if (self.root / name).is_dir():
                identity = (
                    before.application.content_sha256
                    if before is not None and name == "application"
                    else before.base_id
                    if before is not None
                    else "0" * 64
                )
                build_package(
                    self.root / name,
                    name,
                    identity,
                    self.directory / "backup" / f"{name}.deb",
                )
        return {}

    def _install(self, state, checkpoint):
        names = state["replacements"]
        install_packages(
            self.root,
            [self.directory / "incoming" / f"{name}.deb" for name in names],
            resolve_dependencies=True,
        )
        if checkpoint:
            checkpoint("packages-installed")
