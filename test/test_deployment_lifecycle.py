"""Check independent handoff, authentic targets, and user-visible deployment outcomes."""

from dataclasses import replace
import os
from types import SimpleNamespace

import pytest

from runtime.distribution_manifest import ManifestError, read_json
from runtime import deployment_feedback
from update import updater_entry
from update.deployment_transaction import atomic_json, verify_distribution
from update.windows_transaction import WindowsDeploymentTransaction
from test_deployment_transaction import installation, Interrupted


@pytest.mark.parametrize('boundary', ['prepared', 'application:installed', 'manifest-written'])
def test_interrupted_first_install_restores_uninstalled_state(tmp_path, boundary):
    root, staged = tmp_path / 'installed', tmp_path / 'staged'
    root.mkdir()
    target = installation(staged)

    def interrupt(state):
        if state == boundary:
            raise Interrupted()

    with pytest.raises(Interrupted):
        WindowsDeploymentTransaction(root).apply(staged, complete=True, checkpoint=interrupt)
    assert WindowsDeploymentTransaction(root).recover() == 'rolled-back'
    assert not (root / 'distribution.json').exists()
    assert all(not (root / component.name).exists() for component in target.components)


def test_complete_installer_can_explicitly_replace_cpu_with_gpu(tmp_path):
    root, staged = tmp_path / 'installed', tmp_path / 'staged'
    installation(root)
    original = installation(staged)
    target = replace(original, edition='gpu', components=tuple(replace(item, variant='gpu') if item.name == 'inference' else item for item in original.components))
    atomic_json(staged / 'distribution.json', target.to_dict())
    assert WindowsDeploymentTransaction(root).apply(staged, complete=True) == target
    verify_distribution(root, target)


def test_updater_reports_invalid_request_as_failure(tmp_path):
    request = tmp_path / 'request.json'
    atomic_json(request, {'schema': 999})
    with pytest.raises(ManifestError, match='request'):
        updater_entry.run_request(request)
    assert read_json(tmp_path / 'deployment-result.json')['state'] == 'failed'


@pytest.mark.parametrize('authentic', [True, False])
def test_handoff_authenticates_before_replacement_and_waits_for_ui_exit(tmp_path, monkeypatch, authentic):
    root, staged = tmp_path / 'installed', tmp_path / 'staged'
    before = installation(root)
    target = installation(staged, '4.0.0', {name: b'new' for name in ('application', 'inference', 'models')})
    selected = target if authentic else replace(target, version='5.0.0', release_tag='v5.0.0')
    monkeypatch.setattr(updater_entry, 'fetch_component_release', lambda *args, **kwargs: SimpleNamespace(catalog=SimpleNamespace(select=lambda *args: selected)))
    waited = []

    def wait(pid, **kwargs):
        verify_distribution(root, before)
        waited.append(pid)

    monkeypatch.setattr(updater_entry, 'wait_for_exit', wait)
    monkeypatch.setattr(updater_entry, 'validate_installed_worker', lambda root, manifest: verify_distribution(root, manifest))
    monkeypatch.setattr(updater_entry, 'deployment_transaction', WindowsDeploymentTransaction)
    request = tmp_path / 'request.json'
    atomic_json(request, {'schema': 1, 'root': str(root), 'staged': str(staged), 'wait_pid': os.getpid() + 1, 'recover': False})
    if authentic:
        updater_entry.run_request(request)
        assert waited == [os.getpid() + 1]
        assert read_json(tmp_path / 'deployment-result.json')['state'] == 'committed'
        verify_distribution(root, target)
    else:
        with pytest.raises(ManifestError, match='authoritative'):
            updater_entry.run_request(request)
        assert not waited
        verify_distribution(root, before)


def test_deployment_feedback_cleans_only_its_private_staging(tmp_path, monkeypatch):
    cache = tmp_path / 'cache'
    task = cache / 'deployment-task'
    task.mkdir(parents=True)
    staging = cache / 'component-update-task/staged'
    staging.mkdir(parents=True)
    other = cache / 'unrelated'
    other.mkdir()
    atomic_json(task / 'request.json', {'staged': str(staging), 'recover': False})
    result = task / 'deployment-result.json'
    atomic_json(result, {'state': 'committed'})
    monkeypatch.setattr(deployment_feedback, 'app_cache_dir', lambda: cache)
    monkeypatch.setenv('LATEXSNIPPER_DEPLOYMENT_RESULT', str(result))
    feedback, directory = deployment_feedback.consume_deployment_result()
    assert feedback['state'] == 'committed'
    assert deployment_feedback.cleanup_deployment_task(directory)
    assert other.is_dir()


def test_deployment_feedback_rejects_cleanup_outside_task_cache(tmp_path, monkeypatch):
    cache = tmp_path / 'cache'
    task = cache / 'deployment-task'
    task.mkdir(parents=True)
    outside = tmp_path / 'user-documents'
    outside.mkdir()
    atomic_json(task / 'request.json', {'staged': str(outside / 'staged'), 'recover': False})
    monkeypatch.setattr(deployment_feedback, 'app_cache_dir', lambda: cache)
    with pytest.raises(ManifestError, match='escaped'):
        deployment_feedback.cleanup_deployment_task(task)
    assert outside.is_dir()
