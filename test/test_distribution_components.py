"""Exercise shared distribution identities, real inventories and update planning."""

import hashlib
import json
import subprocess
import sys
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from runtime.component_inventory import inventory_component, verify_component
from runtime.distribution_manifest import (
    Artifact,
    Component,
    DistributionManifest,
    FileRecord,
    ManifestError,
    ReleaseCatalog,
)
from update.component_plan import plan_component_update


def component(
    name,
    payload=b"original",
    *,
    edition="cpu",
    protocol=1,
    platform="windows",
    architecture="x86_64",
):
    digest = hashlib.sha256(payload).hexdigest()
    record = FileRecord("resource.bin", digest, len(payload), 0o644)
    return Component(
        name,
        "any" if name == "models" else platform,
        "any" if name == "models" else architecture,
        edition if name == "inference" else "common",
        0 if name == "models" else protocol,
        1,
        (record,),
        Artifact("https://example.com/" + digest + ".zip", digest, len(payload)),
    )


def distribution(
    version="3.1.0",
    *,
    edition="cpu",
    protocol=1,
    application=b"original",
    base_id="1" * 64,
):
    return DistributionManifest(
        version,
        "windows",
        "x86_64",
        edition,
        component("application", application, protocol=protocol),
        base_id,
    )


def test_distribution_round_trip_and_content_identity():
    original = distribution()
    loaded = DistributionManifest.from_dict(json.loads(json.dumps(original.to_dict())))
    assert loaded == original
    application = original.application
    rehosted = replace(
        application,
        artifact=replace(
            application.artifact, url="https://mirror.example.com/artifact.zip"
        ),
    )
    assert rehosted.content_sha256 == application.content_sha256
    assert rehosted.cache_key == application.cache_key


def test_business_update_skips_inference_and_models_across_versions():
    installed = distribution("3.1.0")
    target = distribution("5.0.0", application=b"new application")
    plan = plan_component_update(installed, target)
    assert [item.name for item in plan.downloads] == ["application"]
    assert plan.download_bytes == target.application.artifact.size


def test_fixed_base_change_requires_complete_installer():
    installed = distribution()
    target = distribution("4.0.0", base_id="2" * 64)
    plan = plan_component_update(installed, target)
    assert plan.installer_required
    assert plan.download_bytes == 0


@pytest.mark.parametrize(
    "target",
    [
        distribution(edition="gpu"),
        replace(
            distribution(),
            platform="linux",
            application=component("application", platform="linux"),
        ),
    ],
)
def test_update_cannot_silently_change_installed_target(target):
    with pytest.raises(ManifestError, match="cannot change"):
        plan_component_update(distribution(), target)


def test_cache_identity_separates_cpu_and_gpu_payloads():
    cpu = component("inference")
    gpu = component("inference", edition="gpu")
    assert cpu.cache_key != gpu.cache_key


def test_tampered_inventory_is_rejected_before_update_planning():
    data = distribution().to_dict()
    data["application"]["files"][0]["sha256"] = "1" * 64
    with pytest.raises(ManifestError, match="identity"):
        DistributionManifest.from_dict(data)


@pytest.mark.parametrize("schema", [True, 0, 1, "2"])
def test_unsupported_protocol_schema_is_rejected(schema):
    data = distribution().to_dict()
    data["schema"] = schema
    with pytest.raises(ManifestError):
        DistributionManifest.from_dict(data)


@pytest.mark.parametrize(
    "path", ["../escape", "/absolute", "C:/absolute", "a\\b", "a/../b", "a//b", "a./b"]
)
def test_nonportable_resource_paths_are_rejected(path):
    with pytest.raises(ManifestError):
        FileRecord(path, "0" * 64, 0, 0o644)


def test_inventory_detects_corruption_and_missing_resource(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    file = source / "worker.bin"
    file.write_bytes(b"original worker")
    inventory = inventory_component(source)
    declared = replace(component("inference"), files=inventory)
    assert verify_component(source, declared) == ()
    file.write_bytes(b"corrupt")
    assert verify_component(source, declared) == ("worker.bin",)
    assert verify_component(tmp_path / "missing", declared) == ("worker.bin",)


def test_relative_symlink_identity_and_escape_rejection():
    target = "../lib/python.bin"
    encoded = target.encode("utf-8")
    record = FileRecord(
        "bin/python",
        hashlib.sha256(encoded).hexdigest(),
        len(encoded),
        0o777,
        "symlink",
        target,
    )
    assert record.target == target
    with pytest.raises(ManifestError, match="escapes"):
        replace(record, path="python")


def test_component_rejects_file_and_child_path_conflict():
    parent = FileRecord("native", "0" * 64, 0, 0o644)
    child = FileRecord("native/library.dll", "0" * 64, 0, 0o644)
    with pytest.raises(ManifestError, match="parent"):
        replace(component("inference"), files=(parent, child))


def test_component_builder_packages_real_files_and_stable_identity(tmp_path):
    root = Path(__file__).resolve().parents[1]
    source = tmp_path / "source"
    source.mkdir()
    (source / "resource.bin").write_bytes(b"actual build input")
    command = [
        sys.executable,
        str(root / "scripts/desktop_distribution.py"),
        "component",
        "--source",
        str(source),
        "--output",
        str(tmp_path / "output"),
        "--name",
        "application",
        "--platform",
        "windows",
        "--architecture",
        "x86_64",
        "--variant",
        "common",
        "--worker-protocol",
        "1",
        "--model-format",
        "1",
        "--base-url",
        "https://example.com/release",
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    metadata = Path(report["metadata"])
    declared = Component.from_dict(json.loads(metadata.read_text(encoding="utf-8")))
    archive = metadata.with_suffix("")
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == declared.artifact.sha256
    assert report["uncompressed_bytes"] == len(b"actual build input")
    assert verify_component(source, declared) == ()
    with zipfile.ZipFile(archive) as package:
        assert package.read("resource.bin") == b"actual build input"
    second = subprocess.run(command, capture_output=True, text=True, timeout=20)
    assert second.returncode == 0, second.stderr
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == declared.artifact.sha256


def test_duplicate_json_fields_are_not_silently_accepted(tmp_path):
    path = tmp_path / "distribution.json"
    path.write_text('{"schema":1,"schema":2}', encoding="utf-8")
    with pytest.raises(ManifestError, match="Duplicate JSON"):
        DistributionManifest.load(path)


def test_release_selection_uses_exact_target_and_installer_identity():
    installer = Artifact("https://example.com/setup.exe", "1" * 64, 500)
    cpu = replace(distribution(), installer=installer)
    gpu = replace(
        distribution(edition="gpu"),
        installer=replace(
            installer, url="https://example.com/setup-gpu.exe", sha256="2" * 64
        ),
    )
    catalog = ReleaseCatalog("3.1.0", (cpu, gpu))
    loaded = ReleaseCatalog.from_dict(catalog.to_dict())
    assert loaded.select("windows", "x86_64", "gpu") == gpu
    with pytest.raises(ManifestError, match="No release"):
        loaded.select("linux", "x86_64", "gpu")


def test_public_release_rejects_missing_installer_and_duplicate_targets():
    with pytest.raises(ManifestError, match="first-install"):
        ReleaseCatalog("3.1.0", (distribution(),))
    installed = replace(
        distribution(),
        installer=Artifact("https://example.com/setup.exe", "1" * 64, 500),
    )
    with pytest.raises(ManifestError, match="Duplicate"):
        ReleaseCatalog("3.1.0", (installed, installed))


@pytest.mark.parametrize("entry", ["../escape.txt", "/outside.txt", "C:/outside.txt"])
def test_archive_extractor_rejects_external_members(tmp_path, entry):
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts"))
    from runtime.component_archive import extract_archive

    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr(entry, b"outside")
    with pytest.raises(ManifestError):
        extract_archive(archive, tmp_path / "extracted")


def test_archive_extractor_preserves_real_payload(tmp_path):
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts"))
    from runtime.component_archive import extract_archive

    archive = tmp_path / "payload.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("python/data.bin", b"locked input")
    destination = tmp_path / "extracted"
    extract_archive(archive, destination)
    assert (destination / "python/data.bin").read_bytes() == b"locked input"


def test_download_cache_is_verified_before_reuse(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts"))
    import distribution_archives

    payload = b"verified archive"
    declared = Artifact(
        "https://example.com/archive.zip",
        hashlib.sha256(payload).hexdigest(),
        len(payload),
    )
    target = tmp_path / declared.sha256 / "archive.zip"
    target.parent.mkdir()
    target.write_bytes(payload)
    monkeypatch.setattr(
        distribution_archives.requests,
        "get",
        lambda *a, **kw: pytest.fail("Healthy cache should not download"),
    )
    assert distribution_archives.download_artifact(declared, tmp_path) == target
