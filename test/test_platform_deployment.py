"""Verify native adapter ownership and recovery across interrupted combinations."""

from dataclasses import replace
import shutil
import sys
from types import SimpleNamespace

import pytest

from runtime.component_inventory import inventory_component
from runtime.distribution_manifest import Artifact, BundleSeal, DistributionManifest
from runtime.installation_layout import installation_manifest
from update.deployment_transaction import atomic_json, verify_distribution
from update import debian_transaction, macos_transaction
from test_deployment_transaction import installation, Interrupted


def retarget(manifest, platform):
    return replace(manifest, platform=platform, architecture='arm64' if platform == 'macos' else 'x86_64',
                   components=tuple(replace(item, platform=platform, architecture='arm64' if platform == 'macos' else 'x86_64') for item in manifest.components))


@pytest.fixture
def mac_deployment(tmp_path, monkeypatch):
    bundle = tmp_path / 'LaTeXSnipper.app'
    root = bundle / 'Contents/Resources/desktop'
    before = retarget(installation(root), 'macos')
    atomic_json(root / 'distribution.json', before.to_dict())
    (bundle / 'Contents/Info.plist').write_text(before.version)
    staged = tmp_path / 'staged'
    target = retarget(installation(staged, '4.0.0', {'application': b'new application'}), 'macos')
    for name in ('inference', 'models'):
        shutil.rmtree(staged / name)
    seal = staged / '.bundle-seal'
    (seal / 'Contents/Resources/desktop').mkdir(parents=True)
    (seal / 'Contents/Info.plist').write_text(target.version)
    atomic_json(seal / 'Contents/Resources/desktop/distribution.json', target.installed_identity().to_dict())
    target = replace(target, bundle_seal=BundleSeal(Artifact('https://example.com/seal.zip', 'f' * 64, 100), inventory_component(seal)))
    atomic_json(staged / 'distribution.json', target.to_dict())

    def copy_bundle(arguments, **kwargs):
        assert arguments[0] == 'ditto'
        shutil.copytree(arguments[1], arguments[2])
        return SimpleNamespace(returncode=0, stderr='')

    def check_sealed_identity(candidate):
        identity = DistributionManifest.load(candidate / 'Contents/Resources/desktop/distribution.json')
        assert (candidate / 'Contents/Info.plist').read_text() == identity.version

    monkeypatch.setattr(macos_transaction.subprocess, 'run', copy_bundle)
    # Native bundle verification is exercised against real release artifacts in
    # CI; this fixture tests namespace and journal semantics independently.
    monkeypatch.setattr(macos_transaction, 'verify_bundle', check_sealed_identity)
    if sys.platform != 'darwin':
        def exchange(first, second):
            temporary = first.with_name('exchange-temporary.app')
            first.rename(temporary)
            second.rename(first)
            temporary.rename(second)

        monkeypatch.setattr(macos_transaction, 'exchange_bundles', exchange)
    return root, staged, before, target


@pytest.mark.parametrize('boundary', ['prepared', 'bundle-exchanged', 'committed'])
def test_macos_interruption_restores_one_whole_bundle(mac_deployment, boundary):
    root, staged, before, target = mac_deployment

    def interrupt(state):
        if state == boundary:
            raise Interrupted()

    transaction = macos_transaction.MacOSDeploymentTransaction(root)
    with pytest.raises(Interrupted):
        transaction.apply(staged, checkpoint=interrupt)
    expected = target if boundary == 'committed' else before
    assert transaction.recover() == ('committed' if boundary == 'committed' else 'rolled-back')
    assert DistributionManifest.load(root / 'distribution.json') == expected.installed_identity()
    verify_distribution(root, expected)
    assert transaction.recover() is None


def test_macos_recovery_is_idempotent_after_swap_back(mac_deployment, monkeypatch):
    root, staged, before, target = mac_deployment
    transaction = macos_transaction.MacOSDeploymentTransaction(root)
    with pytest.raises(Interrupted):
        transaction.apply(staged, checkpoint=lambda state: (_ for _ in ()).throw(Interrupted()) if state == 'bundle-exchanged' else None)
    save = transaction._save

    def interrupt_after_exchange(state, status):
        if status == 'rolled-back':
            raise Interrupted()
        save(state, status)

    monkeypatch.setattr(transaction, '_save', interrupt_after_exchange)
    with pytest.raises(Interrupted):
        transaction.recover()
    monkeypatch.setattr(transaction, '_save', save)
    assert transaction.recover() == 'rolled-back'
    verify_distribution(root, before)


def test_macos_seal_tampering_is_rejected_before_exchange(mac_deployment):
    root, staged, before, target = mac_deployment
    (staged / '.bundle-seal/Contents/Info.plist').write_text('tampered')
    from runtime.distribution_manifest import ManifestError

    with pytest.raises(ManifestError, match='authoritative inventory'):
        macos_transaction.MacOSDeploymentTransaction(root).apply(staged)
    verify_distribution(root, before)


@pytest.fixture
def debian_deployment(tmp_path, monkeypatch):
    root = tmp_path / 'prefix/usr/lib/latexsnipper'
    before = retarget(installation(root), 'linux')
    metadata = installation_manifest(root, 'linux')
    metadata.parent.mkdir(parents=True)
    atomic_json(metadata, before.to_dict())
    (root / 'distribution.json').unlink()
    staged = tmp_path / 'staged'
    target = retarget(installation(staged, '4.0.0', {'application': b'new application', 'inference': b'new inference'}), 'linux')
    shutil.rmtree(staged / 'models')
    atomic_json(staged / 'distribution.json', target.to_dict())
    payloads = {}
    database = {item.name: item.content_sha256 for item in before.components}
    fail_next = []

    def build_package(source, component, output, **kwargs):
        snapshot = tmp_path / f'package-{len(payloads)}'
        shutil.copytree(source, snapshot)
        output.write_bytes(b'debian fixture')
        payloads[output] = component, snapshot

    def install_packages(resource_root, packages, **kwargs):
        for package in packages:
            component, snapshot = payloads[package]
            destination = resource_root / component.name
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(snapshot, destination)
            database[component.name] = component.content_sha256
            if fail_next:
                fail_next.pop()
                raise RuntimeError('dpkg interrupted after one package')

    monkeypatch.setattr(debian_transaction, 'build_package', build_package)
    monkeypatch.setattr(debian_transaction, 'install_packages', install_packages)
    return root, staged, before, target, database, fail_next


def test_debian_update_commits_package_database_and_external_identity(debian_deployment):
    root, staged, before, target, database, _ = debian_deployment
    assert debian_transaction.DebianDeploymentTransaction(root).apply(staged) == target
    assert database == {item.name: item.content_sha256 for item in target.components}
    assert DistributionManifest.load(installation_manifest(root, 'linux')) == target
    verify_distribution(root, target)


def test_debian_partial_package_failure_restores_files_and_package_database(debian_deployment):
    root, staged, before, target, database, fail_next = debian_deployment
    fail_next.append(True)
    with pytest.raises(RuntimeError, match='dpkg interrupted'):
        debian_transaction.DebianDeploymentTransaction(root).apply(staged)
    assert database == {item.name: item.content_sha256 for item in before.components}
    assert DistributionManifest.load(installation_manifest(root, 'linux')) == before
    verify_distribution(root, before)


@pytest.mark.parametrize('boundary', ['prepared', 'packages-installed', 'manifest-written'])
def test_debian_process_interruption_recovers_package_ownership(debian_deployment, boundary):
    root, staged, before, target, database, _ = debian_deployment

    def interrupt(state):
        if state == boundary:
            raise Interrupted()

    transaction = debian_transaction.DebianDeploymentTransaction(root)
    with pytest.raises(Interrupted):
        transaction.apply(staged, checkpoint=interrupt)
    assert transaction.recover() == 'rolled-back'
    assert database == {item.name: item.content_sha256 for item in before.components}
    verify_distribution(root, before)
