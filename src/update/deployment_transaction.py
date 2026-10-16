"""Journaled component deployment and recovery, independent of the running UI."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
import json
import logging
import os
from pathlib import Path
import shutil
import time

from runtime.component_inventory import verify_component
from runtime.distribution_manifest import DistributionManifest, ManifestError, read_json
from update.component_plan import plan_component_update

logger = logging.getLogger(f'latexsnipper.{__name__}')
COMPONENT_NAMES = ('application', 'inference', 'models')


def atomic_json(path: Path, value: dict) -> None:
    """Flush state before publishing it; readers see either complete JSON file."""
    temporary = path.with_name(path.name + '.tmp')
    if path.is_symlink() or temporary.is_symlink():
        raise ManifestError('Transaction state cannot be a symbolic link')
    with temporary.open('w', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    if os.name != 'nt':
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def verify_distribution(root: Path, manifest: DistributionManifest) -> None:
    for component in manifest.components:
        damaged = verify_component(root / component.name, component)
        if damaged:
            raise ManifestError(f'Deployed {component.name} failed validation: {damaged[:5]}')


def verify_distribution_sources(root: Path, staged: Path, target: DistributionManifest, replacements: list[str]) -> None:
    for component in target.components:
        source = staged / component.name if component.name in replacements else root / component.name
        if verify_component(source, component):
            raise ManifestError(f'Prepared {component.name} is missing or corrupt')


class DeploymentTransaction:
    """Rename owned components on the same volume and commit identity last."""

    JOURNAL_FIELDS = {'schema', 'status', 'before', 'target', 'replacements', 'present', 'complete'}

    def __init__(self, root: Path):
        if root.is_symlink():
            raise ManifestError('Installation root cannot be a symbolic link')
        self.root = root.resolve(strict=True)
        self.directory = self.root / '.deployment'
        self.lockfile = self.root / '.deployment.lock'
        self.metadata = self.root / 'distribution.json'
        self.journal = self.directory / 'journal.json'
        if self.directory.is_symlink():
            raise ManifestError('Deployment state cannot redirect outside the installation')

    @contextmanager
    def _lock(self, timeout: float = 0) -> Iterator[None]:
        path = self.lockfile
        if path.is_symlink():
            raise ManifestError('Deployment lock cannot be a symbolic link')
        with path.open('a+b') as stream:
            stream.seek(0)
            if os.name == 'nt':
                import msvcrt

                if stream.read(1) == b'':
                    stream.write(b'\0')
                    stream.flush()
                stream.seek(0)
            deadline = time.monotonic() + timeout
            while True:
                try:
                    if os.name == 'nt':
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
                if os.name == 'nt':
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def _remove(self, path: Path) -> None:
        if not path.exists() and not path.is_symlink():
            return
        resolved = path.resolve()
        owned = resolved.is_relative_to(self.root) or resolved == self.directory or resolved.is_relative_to(self.directory)
        if path.is_symlink() or not owned or path == self.root:
            raise ManifestError('Deployment cleanup escaped its installation')
        shutil.rmtree(path)

    def _state(self) -> dict:
        state = read_json(self.journal)
        if set(state) != self.JOURNAL_FIELDS or type(state['schema']) is not int or state['schema'] != 1:
            raise ManifestError('Unsupported deployment journal')
        if state['status'] not in {'prepared', 'applying', 'validating', 'committed', 'rolling-back', 'rolled-back'}:
            raise ManifestError('Unknown deployment state')
        if type(state['complete']) is not bool:
            raise ManifestError('Invalid complete-installation state')
        before = DistributionManifest.from_dict(state['before']) if state['before'] is not None else None
        target = DistributionManifest.from_dict(state['target'])
        if before is None and not state['complete']:
            raise ManifestError('Only a complete installer can initialize an installation')
        if before is not None:
            if state['complete']:
                if before.target[:2] != target.target[:2]:
                    raise ManifestError('Reinstallation cannot change the installation platform or architecture')
            else:
                plan_component_update(before, target)
        names = state['replacements']
        if not isinstance(names, list) or len(names) != len(set(names)) or not set(names) <= set(COMPONENT_NAMES):
            raise ManifestError('Invalid replacement components')
        if not isinstance(state['present'], dict) or set(state['present']) != set(names) or any(type(value) is not bool for value in state['present'].values()):
            raise ManifestError('Invalid original component state')
        return state

    def _save(self, state: dict, status: str) -> None:
        state['status'] = status
        atomic_json(self.journal, state)
        logger.info('发行部署事务 status=%s target=%s', status, state['target']['version'])

    def _rollback(self, state: dict) -> None:
        self._save(state, 'rolling-back')
        saved_entry = self.directory / 'backup/LaTeXSnipper.exe'
        if saved_entry.is_file():
            shutil.copy2(saved_entry, self.directory / 'LaTeXSnipper.exe')
            os.replace(self.directory / 'LaTeXSnipper.exe', self.root / 'LaTeXSnipper.exe')
        for name in reversed(state['replacements']):
            current = self.root / name
            backup = self.directory / 'backup' / name
            incoming = self.directory / 'incoming' / name
            # A backup proves the old directory was moved, even if the process
            # stopped before it could record the next state transition.
            if backup.exists():
                self._remove(current)
                backup.rename(current)
            elif not state['present'][name] and not incoming.exists():
                self._remove(current)
        if state['before'] is None:
            self.metadata.unlink(missing_ok=True)
        else:
            atomic_json(self.metadata, state['before'])
        self._save(state, 'rolled-back')

    def recover(self, *, timeout: float = 0) -> str | None:
        with self._lock(timeout):
            return self._recover()

    def _verify_committed(self, target: DistributionManifest) -> None:
        verify_distribution(self.root, target)

    def _recover(self) -> str | None:
        if not self.journal.exists():
            # No installation files are moved until the first durable journal.
            self._remove(self.directory)
            return None
        state = self._state()
        if state['status'] == 'committed':
            try:
                self._verify_committed(DistributionManifest.from_dict(state['target']))
                outcome = 'committed'
            except ManifestError:
                self._rollback(state)
                outcome = 'rolled-back'
        else:
            self._rollback(state)
            outcome = 'rolled-back'
        self._remove(self.directory)
        return outcome

    def apply(
        self,
        staged: Path,
        *,
        validate: Callable[[Path, DistributionManifest], None] = verify_distribution,
        checkpoint: Callable[[str], None] | None = None,
        complete: bool = False,
    ) -> DistributionManifest:
        """A normal exception rolls back; interrupted processes leave a recoverable journal."""
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
            for component in target.components:
                source = staged / component.name if component.name in names else self.root / component.name
                if verify_component(source, component):
                    raise ManifestError(f'Prepared {component.name} is missing or corrupt')
            expected = {'distribution.json', *names}
            entry_name = 'LaTeXSnipper.exe'
            if complete and (staged / entry_name).is_file():
                expected.add(entry_name)
            if {item.name for item in staged.iterdir()} != expected:
                raise ManifestError('Staging contains unexpected resources')
            required = sum(record.size for component in replacements for record in component.files)
            if shutil.disk_usage(self.root).free < required:
                raise OSError('Insufficient space for deployment and rollback')
            self.directory.mkdir()
            incoming = self.directory / 'incoming'
            backup = self.directory / 'backup'
            incoming.mkdir()
            backup.mkdir()
            for component in replacements:
                shutil.copytree(staged / component.name, incoming / component.name, symlinks=True)
                if verify_component(incoming / component.name, component):
                    raise ManifestError(f'Copied {component.name} failed validation')
            entry = self.root / entry_name
            entry_record = next((item for item in target.component('application').files if item.path == f'bootstrap/{entry_name}'), None)
            if 'application' in names and entry_record is not None and entry.is_file():
                shutil.copy2(entry, backup / entry_name)
            state = {
                'schema': 1, 'status': 'prepared', 'before': before.to_dict() if before else None, 'complete': complete,
                'target': target.to_dict(), 'replacements': names,
                'present': {name: (self.root / name).is_dir() for name in names},
            }
            self._save(state, 'prepared')
            try:
                if checkpoint:
                    checkpoint('prepared')
                self._save(state, 'applying')
                for name in names:
                    current = self.root / name
                    if state['present'][name]:
                        if current.is_symlink():
                            raise ManifestError('Installed components cannot be symbolic links')
                        current.rename(backup / name)
                    if checkpoint:
                        checkpoint(f'{name}:backed-up')
                    (incoming / name).rename(current)
                    if checkpoint:
                        checkpoint(f'{name}:installed')
                self._save(state, 'validating')
                verify_distribution(self.root, target)
                validate(self.root, target)
                if 'application' in names and entry_record is not None:
                    shutil.copy2(self.root / 'application/bootstrap' / entry_name, self.directory / entry_name)
                    os.replace(self.directory / entry_name, entry)
                if checkpoint:
                    checkpoint('validated')
                atomic_json(self.metadata, target.installed_identity().to_dict())
                if checkpoint:
                    checkpoint('manifest-written')
                self._save(state, 'committed')
                if checkpoint:
                    checkpoint('committed')
            except Exception:
                logger.exception('发行部署失败，恢复原组件组合')
                self._rollback(state)
                self._remove(self.directory)
                raise
            self._remove(self.directory)
            return target
