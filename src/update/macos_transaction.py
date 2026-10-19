"""Replace business resources while retaining the signed nested fixed base."""

from __future__ import annotations

import ctypes
import os
import plistlib
import shutil
import subprocess
from pathlib import Path

from runtime.distribution_manifest import DistributionManifest, ManifestError
from runtime.installation_layout import deployment_directory, macos_bundle
from runtime.processes import independent_process_environment
from update.deployment_transaction import (
    DeploymentTransaction,
    atomic_json,
    verify_distribution,
)

DESKTOP = Path("Contents/Resources/desktop")
BASE = Path("Contents/Frameworks/LaTeXSnipperBase.bundle")


def verify_bundle(bundle: Path) -> None:
    arguments = [
        "codesign",
        "--verify",
        "--strict",
        "--verbose=2",
        str(bundle),
    ]
    result = subprocess.run(
        arguments,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        env=independent_process_environment(),
    )
    if result.returncode:
        raise ManifestError(
            f"macOS bundle signature validation failed: {result.stderr or result.stdout}"
        )


def exchange_bundles(first: Path, second: Path) -> None:
    # Darwin's RENAME_SWAP (bsd/sys/stdio.h) is an atomic exchange. Filesystems
    # that cannot perform it fail before either bundle name is changed.
    library = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
    library.renamex_np.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
    library.renamex_np.restype = ctypes.c_int
    if library.renamex_np(os.fsencode(first), os.fsencode(second), 0x00000002):
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


class MacOSDeploymentTransaction(DeploymentTransaction):
    JOURNAL_FIELDS = DeploymentTransaction.JOURNAL_FIELDS | {"original_bundle"}

    def __init__(self, root: Path):
        super().__init__(root)
        self.bundle = macos_bundle(self.root)
        self.owner = self.bundle
        self.directory = deployment_directory(self.root, "macos")
        if self.directory.is_symlink():
            raise ManifestError(
                "Deployment state cannot redirect outside the bundle owner"
            )
        self.journal = self.directory / "journal.json"
        self.lockfile = self.directory.with_suffix(".lock")
        self.candidate = self.directory / self.bundle.name

    def _state(self) -> dict:
        state = super()._state()
        identity = state["original_bundle"]
        if (
            not isinstance(identity, list)
            or len(identity) != 2
            or any(type(v) is not int for v in identity)
        ):
            raise ManifestError("Invalid original bundle identity")
        return state

    def _prepare(self, staged, before, target, replacements) -> dict:
        def ignore(directory, names):
            return [BASE.name] if Path(directory) == self.bundle / BASE.parent else []

        # Only the small outer bundle is copied. The signed fixed base is moved
        # after the UI exits, so neither its files nor weights are traversed.
        shutil.copytree(self.bundle, self.candidate, symlinks=True, ignore=ignore)
        candidate_root = self.candidate / DESKTOP
        if "application" in replacements:
            self._remove(candidate_root / "application")
            shutil.copytree(
                staged / "application", candidate_root / "application", symlinks=True
            )
            shutil.copy2(
                candidate_root / "application/bootstrap/LaTeXSnipper",
                candidate_root / "LaTeXSnipper",
            )
        atomic_json(
            candidate_root / "distribution.json", target.installed_identity().to_dict()
        )
        plist_path = self.candidate / "Contents/Info.plist"
        with plist_path.open("rb") as stream:
            plist = plistlib.load(stream)
        plist.update(
            CFBundleVersion=target.version, CFBundleShortVersionString=target.version
        )
        with plist_path.open("wb") as stream:
            plistlib.dump(plist, stream)
        verify_distribution(candidate_root, target)
        original = self.bundle.stat()
        return {"original_bundle": [original.st_dev, original.st_ino]}

    def _install(self, state, checkpoint):
        source, destination = self.bundle / BASE, self.candidate / BASE
        if source.is_symlink() or destination.exists():
            raise ManifestError("Invalid fixed base ownership")
        source.rename(destination)
        if checkpoint:
            checkpoint("base-retained")
        result = subprocess.run(
            ["codesign", "--force", "--sign", "-", str(self.candidate)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
            env=independent_process_environment(),
        )
        if result.returncode:
            raise ManifestError(f"Local app signing failed: {result.stderr}")
        verify_bundle(self.candidate)
        exchange_bundles(self.bundle, self.candidate)
        if checkpoint:
            checkpoint("bundle-exchanged")

    def _validate_installed(self, target):
        verify_distribution(self.root, target)
        verify_bundle(self.bundle)

    def _publish(self, state):
        if (
            DistributionManifest.load(self.metadata)
            != DistributionManifest.from_dict(state["target"]).installed_identity()
        ):
            raise ManifestError("Installed bundle identity changed before commit")

    def _rollback(self, state):
        self._save(state, "rolling-back")
        original = state["original_bundle"]
        current = self.bundle.stat()
        if [current.st_dev, current.st_ino] != original:
            previous = self.candidate.stat()
            if [previous.st_dev, previous.st_ino] != original:
                raise ManifestError("Original app is unavailable for failure recovery")
            exchange_bundles(self.bundle, self.candidate)
        if not (self.bundle / BASE).exists():
            (self.candidate / BASE).rename(self.bundle / BASE)
        self._save(state, "rolled-back")
