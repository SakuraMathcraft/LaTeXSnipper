"""Exercise combination commits and recovery at every destructive boundary."""

from dataclasses import replace
import json

import pytest

from runtime.component_inventory import inventory_component
from runtime.distribution_manifest import Artifact, Component, DistributionManifest, ManifestError
from update.deployment_transaction import verify_distribution
from update.windows_transaction import WindowsDeploymentTransaction


def installation(root, version='3.0.0', contents=None):
    components = []
    for name in ('application', 'inference', 'models'):
        directory = root / name
        directory.mkdir(parents=True)
        (directory / 'data.bin').write_bytes((contents or {}).get(name, name.encode()))
        components.append(Component(
            name, 'windows', 'x86_64', 'cpu' if name == 'inference' else 'common',
            0 if name == 'models' else 1, 1, inventory_component(directory),
            Artifact(f'https://example.com/{name}.zip', '0' * 64, 1),
        ))
    manifest = DistributionManifest(version, 'windows', 'x86_64', 'cpu', tuple(components))
    (root / 'distribution.json').write_text(json.dumps(manifest.to_dict()), encoding='utf-8')
    return manifest


def test_business_update_commits_only_changed_components(tmp_path):
    root, staged = tmp_path / 'installed', tmp_path / 'staged'
    before = installation(root)
    target = installation(staged, '4.0.0', {'application': b'updated'})
    import shutil

    for name in ('inference', 'models'):
        shutil.rmtree(staged / name)
    retained = (root / 'inference/data.bin').stat().st_ino
    assert WindowsDeploymentTransaction(root).apply(staged) == target
    assert DistributionManifest.load(root / 'distribution.json') == target
    assert (root / 'inference/data.bin').stat().st_ino == retained
    verify_distribution(root, target)
    assert before.component('application') != target.component('application')


def test_committed_cleanup_failure_preserves_success_and_normal_startup(tmp_path, monkeypatch):
    from update.deployment_transaction import needs_recovery

    root, staged = tmp_path / 'installed', tmp_path / 'staged'
    installation(root)
    target = installation(staged, '4.0.0', {name: b'new' for name in ('application', 'inference', 'models')})
    transaction = WindowsDeploymentTransaction(root)
    remove = transaction._remove

    def locked_backup(path):
        if path == transaction.directory / 'backup' and transaction.journal.is_file():
            raise PermissionError('backup still open')
        remove(path)

    with monkeypatch.context() as patch:
        patch.setattr(transaction, '_remove', locked_backup)
        assert transaction.apply(staged) == target
        assert not needs_recovery(transaction.directory)
        assert transaction.recover() == 'committed'
        verify_distribution(root, target)
    assert transaction.recover() == 'committed'
    assert DistributionManifest.load(root / 'distribution.json') == target


def test_same_version_repairs_only_damaged_component(tmp_path):
    root, staged = tmp_path / 'installed', tmp_path / 'staged'
    before = installation(root)
    installation(staged)
    import shutil

    for name in ('application', 'models'):
        shutil.rmtree(staged / name)
    (root / 'inference/data.bin').write_bytes(b'corrupt')
    assert WindowsDeploymentTransaction(root).apply(staged) == before
    verify_distribution(root, before)


def test_validation_failure_restores_entire_original_combination(tmp_path):
    root, staged = tmp_path / 'installed', tmp_path / 'staged'
    before = installation(root)
    installation(staged, '4.0.0', {name: b'new' for name in ('application', 'inference', 'models')})

    def reject(root, manifest):
        raise RuntimeError('worker failed its handshake')

    with pytest.raises(RuntimeError, match='handshake'):
        WindowsDeploymentTransaction(root).apply(staged, validate=reject)
    assert DistributionManifest.load(root / 'distribution.json') == before
    verify_distribution(root, before)
    assert WindowsDeploymentTransaction(root).recover() is None


class Interrupted(BaseException):
    pass


@pytest.mark.parametrize('boundary', [
    'prepared',
    'application:backed-up', 'application:installed',
    'inference:backed-up', 'inference:installed',
    'models:backed-up', 'models:installed', 'validated', 'manifest-written', 'committed',
])
def test_interrupted_deployment_recovers_complete_combination(tmp_path, boundary):
    root, staged = tmp_path / 'installed', tmp_path / 'staged'
    before = installation(root)
    target = installation(staged, '4.0.0', {name: b'new' for name in ('application', 'inference', 'models')})

    def interrupt(state):
        if state == boundary:
            raise Interrupted()

    with pytest.raises(Interrupted):
        WindowsDeploymentTransaction(root).apply(staged, checkpoint=interrupt)
    transaction = WindowsDeploymentTransaction(root)
    expected = target if boundary == 'committed' else before
    outcome = 'committed' if boundary == 'committed' else 'rolled-back'
    assert transaction.recover() == outcome
    assert DistributionManifest.load(root / 'distribution.json') == expected
    verify_distribution(root, expected)
    assert transaction.recover() is None


def test_corrupt_staging_is_rejected_before_installation_changes(tmp_path):
    root, staged = tmp_path / 'installed', tmp_path / 'staged'
    before = installation(root)
    installation(staged, '4.0.0', {name: b'new' for name in ('application', 'inference', 'models')})
    (staged / 'models/data.bin').write_bytes(b'wrong content')
    with pytest.raises(ManifestError, match='missing or corrupt'):
        WindowsDeploymentTransaction(root).apply(staged)
    verify_distribution(root, before)
    assert DistributionManifest.load(root / 'distribution.json') == before


def test_update_cannot_change_installed_edition(tmp_path):
    root, staged = tmp_path / 'installed', tmp_path / 'staged'
    before = installation(root)
    target = installation(staged, '4.0.0')
    target = replace(target, edition='gpu', components=tuple(
        replace(component, variant='gpu') if component.name == 'inference' else component
        for component in target.components
    ))
    (staged / 'distribution.json').write_text(json.dumps(target.to_dict()), encoding='utf-8')
    with pytest.raises(ManifestError, match='edition'):
        WindowsDeploymentTransaction(root).apply(staged)
    verify_distribution(root, before)
