"""Exercise combination commits and recovery at every destructive boundary."""

import json
from dataclasses import replace

import pytest

from runtime.component_inventory import inventory_component
from runtime.distribution_manifest import (
    Artifact,
    Component,
    DistributionManifest,
    ManifestError,
)
from update.deployment_transaction import verify_distribution
from update.windows_transaction import WindowsDeploymentTransaction


def installation(root, version="3.0.0", contents=None, *, full=True):
    names = (
        ("application", "runtime", "inference", "models") if full else ("application",)
    )
    for name in names:
        directory = root / name
        directory.mkdir(parents=True)
        (directory / "data.bin").write_bytes((contents or {}).get(name, name.encode()))
    application = Component(
        "application",
        "windows",
        "x86_64",
        "common",
        1,
        1,
        inventory_component(root / "application"),
        Artifact("https://example.com/application.zip", "0" * 64, 1),
    )
    manifest = DistributionManifest(
        version, "windows", "x86_64", "cpu", application, "1" * 64
    )
    (root / "distribution.json").write_text(
        json.dumps(manifest.to_dict()), encoding="utf-8"
    )
    return manifest


def test_business_update_commits_only_changed_components(tmp_path):
    root, staged = tmp_path / "installed", tmp_path / "staged"
    before = installation(root)
    target = installation(staged, "4.0.0", {"application": b"updated"}, full=False)
    retained = (root / "inference/data.bin").stat().st_ino
    assert WindowsDeploymentTransaction(root).apply(staged) == target
    assert DistributionManifest.load(root / "distribution.json") == target
    assert (root / "inference/data.bin").stat().st_ino == retained
    verify_distribution(root, target)
    assert before.application != target.application


def test_committed_cleanup_failure_preserves_success_and_normal_startup(
    tmp_path, monkeypatch
):
    from update.deployment_transaction import needs_recovery

    root, staged = tmp_path / "installed", tmp_path / "staged"
    installation(root)
    target = installation(
        staged,
        "4.0.0",
        {"application": b"new"},
        full=False,
    )
    transaction = WindowsDeploymentTransaction(root)
    remove = transaction._remove

    def locked_backup(path):
        if path == transaction.directory / "backup" and transaction.journal.is_file():
            raise PermissionError("backup still open")
        remove(path)

    with monkeypatch.context() as patch:
        patch.setattr(transaction, "_remove", locked_backup)
        assert transaction.apply(staged) == target
        assert not needs_recovery(transaction.directory)
        assert transaction.recover() == "committed"
        verify_distribution(root, target)
    assert transaction.recover() == "committed"
    assert DistributionManifest.load(root / "distribution.json") == target


def test_validation_failure_restores_entire_original_combination(tmp_path):
    root, staged = tmp_path / "installed", tmp_path / "staged"
    before = installation(root)
    installation(
        staged,
        "4.0.0",
        {"application": b"new"},
        full=False,
    )

    def reject(root, manifest):
        raise RuntimeError("worker failed its handshake")

    with pytest.raises(RuntimeError, match="handshake"):
        WindowsDeploymentTransaction(root).apply(staged, validate=reject)
    assert DistributionManifest.load(root / "distribution.json") == before
    verify_distribution(root, before)
    assert WindowsDeploymentTransaction(root).recover() is None


class Interrupted(BaseException):
    pass


@pytest.mark.parametrize(
    "boundary",
    [
        "prepared",
        "application:backed-up",
        "application:installed",
        "validated",
        "manifest-written",
        "committed",
    ],
)
def test_interrupted_deployment_recovers_complete_combination(tmp_path, boundary):
    root, staged = tmp_path / "installed", tmp_path / "staged"
    before = installation(root)
    target = installation(
        staged,
        "4.0.0",
        {"application": b"new"},
        full=False,
    )

    def interrupt(state):
        if state == boundary:
            raise Interrupted()

    with pytest.raises(Interrupted):
        WindowsDeploymentTransaction(root).apply(staged, checkpoint=interrupt)
    transaction = WindowsDeploymentTransaction(root)
    expected = target if boundary == "committed" else before
    outcome = "committed" if boundary == "committed" else "rolled-back"
    assert transaction.recover() == outcome
    assert DistributionManifest.load(root / "distribution.json") == expected
    verify_distribution(root, expected)
    assert transaction.recover() is None


def test_corrupt_staging_is_rejected_before_installation_changes(tmp_path):
    root, staged = tmp_path / "installed", tmp_path / "staged"
    before = installation(root)
    installation(
        staged,
        "4.0.0",
        {"application": b"new"},
        full=False,
    )
    (staged / "application/data.bin").write_bytes(b"wrong content")
    with pytest.raises(ManifestError, match="validation"):
        WindowsDeploymentTransaction(root).apply(staged)
    verify_distribution(root, before)
    assert DistributionManifest.load(root / "distribution.json") == before


def test_update_cannot_change_installed_edition(tmp_path):
    root, staged = tmp_path / "installed", tmp_path / "staged"
    before = installation(root)
    target = installation(staged, "4.0.0", full=False)
    target = replace(target, edition="gpu")
    (staged / "distribution.json").write_text(
        json.dumps(target.to_dict()), encoding="utf-8"
    )
    with pytest.raises(ManifestError, match="edition"):
        WindowsDeploymentTransaction(root).apply(staged)
    verify_distribution(root, before)


def test_business_replacement_removes_obsolete_owned_files_and_keeps_fixed_data(
    tmp_path,
):
    root, staged = tmp_path / "installed", tmp_path / "staged"
    before = installation(root)
    obsolete = root / "application/retired.py"
    obsolete.write_bytes(b"retired business code")
    before = replace(
        before,
        application=replace(
            before.application, files=inventory_component(root / "application")
        ),
    )
    (root / "distribution.json").write_text(
        json.dumps(before.to_dict()), encoding="utf-8"
    )
    user_data = root.parent / "user-data/settings.json"
    user_data.parent.mkdir()
    user_data.write_bytes(b"user preferences")
    fixed = root / "models/data.bin"
    fixed.write_bytes(b"unreadable to an update checker")
    retained = fixed.stat().st_ino
    target = installation(staged, "4.0.0", {"application": b"new"}, full=False)
    WindowsDeploymentTransaction(root).apply(staged)
    assert {p.name for p in (root / "application").iterdir()} == {"data.bin"}
    assert (root / "application/data.bin").read_bytes() == b"new"
    assert (
        fixed.stat().st_ino == retained
        and user_data.read_bytes() == b"user preferences"
    )
    assert DistributionManifest.load(root / "distribution.json") == target


@pytest.mark.parametrize("fail", [True, False])
def test_complete_install_replaces_owned_files_without_parsing_old_metadata(
    tmp_path, fail
):
    root, staged = tmp_path / "installed", tmp_path / "staged"
    installation(root)
    previous = b"unreadable installation metadata \xff"
    (root / "distribution.json").write_bytes(previous)
    target = installation(staged, "4.0.0", {"runtime": b"new fixed runtime"})

    def validate(*args):
        if fail:
            raise RuntimeError("installation interrupted")

    transaction = WindowsDeploymentTransaction(root)
    if fail:
        with pytest.raises(RuntimeError):
            transaction.apply(staged, complete=True, validate=validate)
        assert (root / "distribution.json").read_bytes() == previous
        assert (root / "runtime/data.bin").read_bytes() == b"runtime"
    else:
        transaction.apply(staged, complete=True, validate=validate)
        assert DistributionManifest.load(root / "distribution.json") == target
        assert (root / "runtime/data.bin").read_bytes() == b"new fixed runtime"
