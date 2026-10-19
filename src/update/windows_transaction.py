"""Replace Windows components by same-volume directory renames."""

import os
import shutil

from runtime.component_inventory import verify_component
from runtime.distribution_manifest import ManifestError
from update.deployment_transaction import DeploymentTransaction


class WindowsDeploymentTransaction(DeploymentTransaction):
    def _prepare(self, staged, before, target, replacements) -> dict:
        required = sum(
            path.stat().st_size
            for name in replacements
            for path in (staged / name).rglob("*")
            if path.is_file()
        )
        if shutil.disk_usage(self.root).free < required:
            raise OSError("Insufficient space for deployment and failure recovery")
        incoming, backup = self.directory / "incoming", self.directory / "backup"
        incoming.mkdir()
        backup.mkdir()
        for name in replacements:
            shutil.copytree(staged / name, incoming / name, symlinks=True)
            if name == "application" and verify_component(
                incoming / name, target.application
            ):
                raise ManifestError("Copied application failed validation")
        entry = self.root / "LaTeXSnipper.exe"
        if "application" in replacements and entry.is_file():
            shutil.copy2(entry, backup / entry.name)
        return {}

    def _install(self, state, checkpoint):
        for name in state["replacements"]:
            current = self.root / name
            if state["present"][name]:
                if current.is_symlink():
                    raise ManifestError("Installed components cannot be symbolic links")
                current.rename(self.directory / "backup" / name)
            if checkpoint:
                checkpoint(f"{name}:backed-up")
            (self.directory / "incoming" / name).rename(current)
            if checkpoint:
                checkpoint(f"{name}:installed")

    def _publish(self, state):
        if "application" in state["replacements"]:
            entry = self.root / "application/bootstrap/LaTeXSnipper.exe"
            if entry.is_file():
                shutil.copy2(entry, self.directory / entry.name)
                os.replace(self.directory / entry.name, self.root / entry.name)
        super()._publish(state)

    def _rollback(self, state: dict) -> None:
        self._save(state, "rolling-back")
        saved_entry = self.directory / "backup/LaTeXSnipper.exe"
        if saved_entry.is_file():
            shutil.copy2(saved_entry, self.directory / "LaTeXSnipper.exe")
            os.replace(
                self.directory / "LaTeXSnipper.exe", self.root / "LaTeXSnipper.exe"
            )
        for name in reversed(state["replacements"]):
            current = self.root / name
            backup = self.directory / "backup" / name
            incoming = self.directory / "incoming" / name
            # A backup proves the old directory was moved, even if the process
            # stopped before it could record the next state transition.
            if backup.exists():
                self._remove(current)
                backup.rename(current)
            elif not state["present"][name] and not incoming.exists():
                self._remove(current)
        self._restore_identity(state)
