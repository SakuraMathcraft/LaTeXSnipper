"""Journaled component deployment and recovery, independent of the running UI."""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from runtime.component_inventory import verify_component
from runtime.distribution_manifest import DistributionManifest, ManifestError, read_json
from update.component_plan import plan_component_update

logger = logging.getLogger(f"latexsnipper.{__name__}")
COMPONENT_NAMES = ("application", "runtime", "inference", "models")


def atomic_bytes(path: Path, data: bytes) -> None:
    """Flush state before publishing it; readers see one complete snapshot."""
    temporary = path.with_name(path.name + ".tmp")
    if path.is_symlink() or temporary.is_symlink():
        raise ManifestError("Transaction state cannot be a symbolic link")
    with temporary.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    if os.name != "nt":
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def atomic_json(path: Path, value: dict) -> None:
    atomic_bytes(
        path,
        (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
            "utf-8"
        ),
    )


def verify_distribution(root: Path, manifest: DistributionManifest) -> None:
    damaged = verify_component(root / "application", manifest.application)
    if damaged:
        raise ManifestError(f"Deployed application failed validation: {damaged[:5]}")


class DeploymentTransaction(ABC):
    """Own deployment planning, durable state and the common commit lifecycle."""

    JOURNAL_FIELDS = {
        "schema",
        "status",
        "before",
        "target",
        "replacements",
        "present",
        "complete",
    }

    def __init__(self, root: Path):
        if root.is_symlink():
            raise ManifestError("Installation root cannot be a symbolic link")
        self.root = root.resolve(strict=True)
        self.owner = self.root
        self.directory = self.root / ".deployment"
        self.lockfile = self.root / ".deployment.lock"
        self.metadata = self.root / "distribution.json"
        self.journal = self.directory / "journal.json"
        if self.directory.is_symlink():
            raise ManifestError(
                "Deployment state cannot redirect outside the installation"
            )

    @contextmanager
    def _lock(self, timeout: float = 0) -> Iterator[None]:
        path = self.lockfile
        if path.is_symlink():
            raise ManifestError("Deployment lock cannot be a symbolic link")
        with path.open("a+b") as stream:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt

                if stream.read(1) == b"":
                    stream.write(b"\0")
                    stream.flush()
                stream.seek(0)
            deadline = time.monotonic() + timeout
            while True:
                try:
                    if os.name == "nt":
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except (BlockingIOError, PermissionError):
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.1)
            try:
                yield
            finally:
                if os.name == "nt":
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def _remove(self, path: Path) -> None:
        if not path.exists() and not path.is_symlink():
            return
        resolved = path.resolve()
        owned = (
            resolved.is_relative_to(self.root)
            or resolved == self.directory
            or resolved.is_relative_to(self.directory)
        )
        if path.is_symlink() or not owned or path == self.root:
            raise ManifestError("Deployment cleanup escaped its installation")
        shutil.rmtree(path)

    def _state(self) -> dict:
        state = read_json(self.journal)
        if (
            set(state) != self.JOURNAL_FIELDS
            or type(state["schema"]) is not int
            or state["schema"] != 1
        ):
            raise ManifestError("Unsupported deployment journal")
        if state["status"] not in {
            "prepared",
            "applying",
            "validating",
            "committed",
            "rolling-back",
            "rolled-back",
        }:
            raise ManifestError("Unknown deployment state")
        if type(state["complete"]) is not bool:
            raise ManifestError("Invalid complete-installation state")
        target = DistributionManifest.from_dict(state["target"])
        if state["complete"]:
            if state["before"] is not None:
                if not isinstance(state["before"], str):
                    raise ManifestError("Invalid installer metadata snapshot")
                try:
                    bytes.fromhex(state["before"])
                except ValueError as exc:
                    raise ManifestError("Invalid installer metadata snapshot") from exc
        else:
            before = DistributionManifest.from_dict(state["before"])
            if plan_component_update(before, target).installer_required:
                raise ManifestError("Fixed base changed; use the complete installer")
        names = state["replacements"]
        if (
            not isinstance(names, list)
            or len(names) != len(set(names))
            or not set(names) <= set(COMPONENT_NAMES)
        ):
            raise ManifestError("Invalid replacement components")
        if (
            not isinstance(state["present"], dict)
            or set(state["present"]) != set(names)
            or any(type(value) is not bool for value in state["present"].values())
        ):
            raise ManifestError("Invalid original component state")
        return state

    def _save(self, state: dict, status: str) -> None:
        state["status"] = status
        atomic_json(self.journal, state)
        logger.info(
            "发行部署事务 status=%s target=%s", status, state["target"]["version"]
        )

    @abstractmethod
    def _rollback(self, state: dict) -> None:
        raise NotImplementedError

    def _restore_identity(self, state: dict) -> None:
        if state["before"] is None:
            self.metadata.unlink(missing_ok=True)
        elif state["complete"]:
            atomic_bytes(self.metadata, bytes.fromhex(state["before"]))
        else:
            atomic_json(self.metadata, state["before"])
        self._save(state, "rolled-back")

    def _cleanup_completed(self) -> None:
        try:
            # Keep the durable outcome until every backup has been removed.
            for child in self.directory.iterdir():
                if child == self.journal:
                    continue
                if child.is_dir() and not child.is_symlink():
                    self._remove(child)
                else:
                    child.unlink()
            self.journal.unlink(missing_ok=True)
            self.directory.rmdir()
        except OSError:
            logger.warning("部署已结束，暂存清理将在下次更新时重试", exc_info=True)

    def recover(self, *, timeout: float = 0) -> str | None:
        with self._lock(timeout):
            return self._recover()

    def _validate_installed(self, target: DistributionManifest) -> None:
        verify_distribution(self.root, target)

    def _recover(self) -> str | None:
        if not self.journal.exists():
            self._remove(self.directory)
            return None
        state = self._state()
        if state["status"] == "committed":
            outcome = "committed"
        elif state["status"] == "rolled-back":
            outcome = "rolled-back"
        else:
            self._rollback(state)
            outcome = "rolled-back"
        self._cleanup_completed()
        return outcome

    @abstractmethod
    def _prepare(self, staged, before, target, replacements) -> dict:
        raise NotImplementedError

    @abstractmethod
    def _install(self, state, checkpoint) -> None:
        raise NotImplementedError

    def _publish(self, state: dict) -> None:
        self.metadata.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(
            self.metadata,
            DistributionManifest.from_dict(state["target"])
            .installed_identity()
            .to_dict(),
        )

    def apply(
        self, staged: Path, *, validate=None, checkpoint=None, complete: bool = False
    ) -> DistributionManifest:
        """Commit a validated combination; only unfinished transactions can roll back."""
        staged = staged.resolve(strict=True)
        owner = self.owner
        if staged.is_relative_to(owner) or owner.is_relative_to(staged):
            raise ManifestError("Staging must be separate from the installation")
        with self._lock():
            self._recover()
            if self.directory.exists():
                raise ManifestError("Previous deployment cleanup is still pending")
            if self.metadata.is_symlink():
                raise ManifestError("Installation metadata cannot be a symbolic link")
            before = (
                DistributionManifest.load(self.metadata)
                if self.metadata.is_file() and not complete
                else None
            )
            original_metadata = (
                self.metadata.read_bytes().hex()
                if complete and self.metadata.is_file()
                else None
            )
            target = DistributionManifest.load(staged / "distribution.json")
            if complete:
                if target.platform == "macos":
                    raise ManifestError(
                        "Install a complete macOS app from its signed carrier"
                    )
                replacements = list(COMPONENT_NAMES)
            else:
                if before is None:
                    raise ManifestError(
                        "Updating requires an existing installation identity"
                    )
                plan = plan_component_update(before, target)
                if plan.installer_required:
                    raise ManifestError(
                        "Fixed base changed; use the complete installer"
                    )
                replacements = [item.name for item in plan.downloads]
            names = list(replacements)
            if {item.name for item in staged.iterdir()} != {
                "distribution.json",
                *names,
            }:
                raise ManifestError("Staging contains unexpected resources")
            if "application" in names:
                verify_distribution(staged, target)
            self.directory.mkdir()
            try:
                extra = self._prepare(staged, before, target, replacements)
            except Exception:
                self._cleanup_completed()
                raise
            state = {
                "schema": 1,
                "status": "prepared",
                "before": original_metadata
                if complete
                else before.to_dict()
                if before
                else None,
                "target": target.to_dict(),
                "complete": complete,
                "replacements": names,
                "present": {name: (self.root / name).is_dir() for name in names},
                **extra,
            }
            self._save(state, "prepared")
            try:
                if checkpoint:
                    checkpoint("prepared")
                self._save(state, "applying")
                self._install(state, checkpoint)
                self._save(state, "validating")
                self._validate_installed(target)
                if validate is not None:
                    validate(self.root, target)
                if checkpoint:
                    checkpoint("validated")
                self._publish(state)
                if checkpoint:
                    checkpoint("manifest-written")
                self._save(state, "committed")
            except Exception:
                logger.exception("发行部署失败，恢复原组件组合")
                self._rollback(state)
                self._cleanup_completed()
                raise
            if checkpoint:
                checkpoint("committed")
            self._cleanup_completed()
            return target


def needs_recovery(directory: Path) -> bool:
    if not directory.exists():
        return False
    journal = directory / "journal.json"
    if not journal.is_file():
        # Preparing a deployment never mutates installed resources before the
        # first journal. Leftover staging can be cleaned on the next update.
        return False
    return read_json(journal).get("status") not in {"committed", "rolled-back"}
