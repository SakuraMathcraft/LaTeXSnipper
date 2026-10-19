"""Exercise platform file ownership and business-only failure recovery."""

import plistlib
import shutil
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from runtime.component_inventory import inventory_component
from runtime.distribution_manifest import DistributionManifest
from runtime.installation_layout import installation_manifest
from test_deployment_transaction import Interrupted, installation
from update import debian_transaction, macos_transaction
from update.deployment_transaction import atomic_json, verify_distribution


def retarget(manifest, platform):
    architecture = "arm64" if platform == "macos" else "x86_64"
    return replace(
        manifest,
        platform=platform,
        architecture=architecture,
        application=replace(
            manifest.application, platform=platform, architecture=architecture
        ),
    )


@pytest.fixture
def mac_deployment(tmp_path, monkeypatch):
    bundle = tmp_path / "LaTeXSnipper.app"
    root = bundle / macos_transaction.DESKTOP
    before = retarget(installation(root, full=False), "macos")
    bootstrap = root / "application/bootstrap/LaTeXSnipper"
    bootstrap.parent.mkdir()
    bootstrap.write_bytes(b"old launcher")
    bootstrap.chmod(0o755)
    shutil.copy2(bootstrap, root / "LaTeXSnipper")
    before = replace(
        before,
        application=replace(
            before.application, files=inventory_component(root / "application")
        ),
    )
    atomic_json(root / "distribution.json", before.to_dict())
    with (bundle / "Contents/Info.plist").open("wb") as stream:
        plistlib.dump({"CFBundleVersion": before.version}, stream)
    fixed = bundle / macos_transaction.BASE
    fixed.mkdir(parents=True)
    (fixed / "weights.onnx").write_bytes(b"fixed weights")
    staged = tmp_path / "staged"
    target = retarget(
        installation(staged, "4.0.0", {"application": b"new"}, full=False), "macos"
    )
    bootstrap = staged / "application/bootstrap/LaTeXSnipper"
    bootstrap.parent.mkdir()
    bootstrap.write_bytes(b"new launcher")
    bootstrap.chmod(0o755)
    target = replace(
        target,
        application=replace(
            target.application, files=inventory_component(staged / "application")
        ),
    )
    atomic_json(staged / "distribution.json", target.to_dict())

    def native_tool(arguments, **kwargs):
        assert arguments[0] == "codesign" and "--deep" not in arguments
        if "--force" in arguments:
            candidate_root = Path(arguments[-1]) / macos_transaction.DESKTOP
            assert (candidate_root / "LaTeXSnipper").read_bytes() == b"new launcher"
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(macos_transaction.subprocess, "run", native_tool)
    if sys.platform != "darwin":

        def exchange(first, second):
            temporary = first.with_name("exchange-temporary.app")
            first.rename(temporary)
            second.rename(first)
            temporary.rename(second)

        monkeypatch.setattr(macos_transaction, "exchange_bundles", exchange)
    return root, staged, before, target


@pytest.mark.parametrize(
    "boundary", ["prepared", "base-retained", "bundle-exchanged", "committed"]
)
def test_macos_interruption_recovers_business_and_retains_fixed_base(
    mac_deployment, boundary
):
    root, staged, before, target = mac_deployment
    transaction = macos_transaction.MacOSDeploymentTransaction(root)
    weights = transaction.bundle / macos_transaction.BASE / "weights.onnx"
    identity = weights.stat().st_ino

    def interrupt(state):
        if state == boundary:
            raise Interrupted()

    with pytest.raises(Interrupted):
        transaction.apply(staged, checkpoint=interrupt)
    expected = target if boundary == "committed" else before
    assert transaction.recover() == (
        "committed" if boundary == "committed" else "rolled-back"
    )
    assert (
        DistributionManifest.load(root / "distribution.json")
        == expected.installed_identity()
    )
    assert (
        weights.stat().st_ino == identity and weights.read_bytes() == b"fixed weights"
    )
    verify_distribution(root, expected)
    assert (root / "LaTeXSnipper").read_bytes() == (
        root / "application/bootstrap/LaTeXSnipper"
    ).read_bytes()
    assert transaction.recover() is None


def test_macos_signing_failure_preserves_original_app(mac_deployment, monkeypatch):
    root, staged, before, _ = mac_deployment
    monkeypatch.setattr(
        macos_transaction.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=1, stderr="sign failed"),
    )
    with pytest.raises(ValueError, match="signing failed"):
        macos_transaction.MacOSDeploymentTransaction(root).apply(staged)
    verify_distribution(root, before)
    assert (root / "LaTeXSnipper").read_bytes() == b"old launcher"
    assert (
        macos_transaction.macos_bundle(root) / macos_transaction.BASE / "weights.onnx"
    ).read_bytes() == b"fixed weights"


@pytest.fixture
def debian_deployment(tmp_path, monkeypatch):
    root = tmp_path / "prefix/usr/lib/latexsnipper"
    before = retarget(installation(root), "linux")
    metadata = installation_manifest(root, "linux")
    metadata.parent.mkdir(parents=True)
    atomic_json(metadata, before.to_dict())
    (root / "distribution.json").unlink()
    staged = tmp_path / "staged"
    target = retarget(
        installation(staged, "4.0.0", {"application": b"new"}, full=False), "linux"
    )
    atomic_json(staged / "distribution.json", target.to_dict())
    payloads, installed = {}, []

    def build_package(source, name, identity, output):
        snapshot = tmp_path / f"package-{len(payloads)}"
        shutil.copytree(source, snapshot)
        output.write_bytes(b"package")
        payloads[output] = name, snapshot

    def install_packages(resource_root, packages, **kwargs):
        for package in packages:
            name, snapshot = payloads[package]
            installed.append(name)
            shutil.rmtree(resource_root / name)
            shutil.copytree(snapshot, resource_root / name)

    monkeypatch.setattr(debian_transaction, "build_package", build_package)
    monkeypatch.setattr(debian_transaction, "install_packages", install_packages)
    return root, staged, before, target, installed


def test_debian_update_changes_only_business_package(debian_deployment):
    root, staged, _, target, packages = debian_deployment
    retained = (root / "models/data.bin").stat().st_ino
    debian_transaction.DebianDeploymentTransaction(root).apply(staged)
    assert packages == ["application"]
    assert (root / "models/data.bin").stat().st_ino == retained
    assert (
        DistributionManifest.load(installation_manifest(root, "linux"))
        == target.installed_identity()
    )


def test_debian_failed_validation_restores_business_package_and_metadata(
    debian_deployment,
):
    root, staged, before, _, packages = debian_deployment

    def reject(*args):
        raise RuntimeError("business failed")

    with pytest.raises(RuntimeError):
        debian_transaction.DebianDeploymentTransaction(root).apply(
            staged, validate=reject
        )
    assert packages == ["application", "application"]
    verify_distribution(root, before)
    assert DistributionManifest.load(installation_manifest(root, "linux")) == before
