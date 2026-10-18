"""Package and publish immutable desktop resources."""

import argparse
import json
import stat
import subprocess
import sys
import zipfile
from argparse import Namespace
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

from desktop_distribution import build_component, write_json  # noqa: E402
from release_installers import link_or_copy  # noqa: E402
from runtime.component_inventory import file_sha256, inventory_component  # noqa: E402
from runtime.distribution_manifest import (  # noqa: E402
    Artifact,
    BundleSeal,
    Component,
    DistributionManifest,
    ManifestError,
    ReleaseCatalog,
    read_json,
)


def artifact(path: Path, base_url: str) -> Artifact:
    if path.stat().st_size >= 2**31:
        raise ManifestError(f"Release asset exceeds GitHub's 2 GiB limit: {path.name}")
    return Artifact(f"{base_url}/{path.name}", file_sha256(path), path.stat().st_size)


def package_component(
    source: Path, output: Path, name: str, target: str, variant: str, base_url: str
) -> Component:
    platform, architecture = target.split("-")
    from mathcraft_ocr.protocol import MODEL_FORMAT, WORKER_PROTOCOL

    stamp = source.parent / "stamp.json"
    if stamp.is_file():
        component = Component.from_dict(read_json(stamp)["component"])
        filename = component.artifact.url.rsplit("/", 1)[-1]
        link_or_copy(source.parent / filename, output / filename)
        return replace(
            component,
            artifact=replace(component.artifact, url=f"{base_url}/{filename}"),
        )

    records_before = set(
        output.glob(f"{name}-{platform}-{architecture}-{variant}-*.zip.json")
    )
    build_component(
        Namespace(
            source=source,
            output=output,
            name=name,
            platform=platform,
            architecture=architecture,
            variant=variant,
            worker_protocol=0 if name == "models" else WORKER_PROTOCOL,
            model_format=MODEL_FORMAT,
            base_url=base_url,
        )
    )
    records = set(output.glob(f"{name}-{platform}-{architecture}-{variant}-*.zip.json"))
    changed = records - records_before
    if len(changed) != 1:
        raise ManifestError("Component packaging requires a fresh output directory")
    component = Component.from_dict(read_json(changed.pop()))
    filename = component.artifact.url.rsplit("/", 1)[-1]
    if source.parent.resolve() != output.resolve():
        link_or_copy(output / filename, source.parent / filename)
    return component


def package_bundle_seal(bundle: Path, output: Path, base_url: str) -> BundleSeal:
    excluded = tuple(
        Path("Contents/Resources/desktop") / name
        for name in ("application", "inference", "models")
    )
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(bundle.rglob("*")):
            relative = path.relative_to(bundle)
            if any(
                relative == prefix or relative.is_relative_to(prefix)
                for prefix in excluded
            ):
                continue
            if path.is_dir() and not path.is_symlink():
                continue
            entry = zipfile.ZipInfo(
                relative.as_posix(), date_time=(1980, 1, 1, 0, 0, 0)
            )
            entry.create_system = 3
            mode = stat.S_IFLNK if path.is_symlink() else stat.S_IFREG
            entry.external_attr = (mode | stat.S_IMODE(path.lstat().st_mode)) << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(
                entry,
                path.readlink().as_posix().encode()
                if path.is_symlink()
                else path.read_bytes(),
            )
    files = tuple(
        record
        for record in inventory_component(bundle)
        if not any(
            Path(record.path) == prefix or Path(record.path).is_relative_to(prefix)
            for prefix in excluded
        )
    )
    return BundleSeal(artifact(output, base_url), files)


def publish_catalog(directory: Path, version: str, output: Path) -> ReleaseCatalog:
    distributions = tuple(
        DistributionManifest.load(path)
        for path in sorted(directory.glob("distribution-*.json"))
    )
    catalog = ReleaseCatalog(version, distributions)
    expected = {
        ("windows", "x86_64", "cpu"),
        ("windows", "x86_64", "gpu"),
        ("linux", "x86_64", "cpu"),
        ("linux", "x86_64", "gpu"),
        ("macos", "arm64", "cpu"),
    }
    if {item.target for item in distributions} != expected:
        raise ManifestError(
            "Release does not contain all five declared desktop distributions"
        )
    write_json(output, catalog.to_dict())
    return catalog


def publish_release(directory: Path, version: str, tag: str) -> None:
    catalog_path = directory / "desktop-release.json"
    catalog = publish_catalog(directory, version, catalog_path)
    names = {
        catalog_path.name,
        f"LaTeXSnipperOffice_{version}_amd64.exe",
        "LaTeXSnipper_User_Manual.pdf",
    }
    for distribution in catalog.distributions:
        resources = [component.artifact for component in distribution.components]
        if distribution.installer is None:
            raise ManifestError("Release is missing its installer")
        resources.append(distribution.installer)
        if distribution.bundle_seal:
            resources.append(distribution.bundle_seal.artifact)
        names.update(resource.url.rsplit("/", 1)[-1] for resource in resources)
    subprocess.run(
        ["gh", "release", "upload", tag, str(catalog_path), "--clobber"], check=True
    )
    assets = json.loads(
        subprocess.check_output(
            ["gh", "release", "view", tag, "--json", "assets"], encoding="utf-8"
        )
    )["assets"]
    for asset in assets:
        if asset["name"] not in names:
            subprocess.run(
                ["gh", "release", "delete-asset", tag, asset["name"], "--yes"],
                check=True,
            )
    subprocess.run(
        ["gh", "release", "edit", tag, "--draft=false", "--latest"], check=True
    )


def upload_desktop_assets(directory: Path, tag: str) -> None:
    from urllib.parse import unquote, urlsplit

    resources = set()
    for path in directory.glob("distribution-*.json"):
        distribution = DistributionManifest.load(path)
        if distribution.installer is None:
            raise ManifestError("Release is missing its installer")
        resources.add(distribution.installer)
        resources.update(
            component.artifact
            for component in distribution.components
            if component.name != "models"
        )
        if distribution.bundle_seal:
            resources.add(distribution.bundle_seal.artifact)
    paths = [
        directory / unquote(urlsplit(resource.url).path.rsplit("/", 1)[-1])
        for resource in sorted(resources, key=lambda item: item.url)
    ]
    if not paths:
        raise ManifestError("No desktop release assets")
    for path in paths:
        if path.stat().st_size >= 2**31:
            raise ManifestError(
                f"Release asset exceeds GitHub's 2 GiB limit: {path.name}"
            )
    subprocess.run(
        ["gh", "release", "upload", tag, "--clobber", *map(str, paths)], check=True
    )


def finalize_windows(directory: Path, signed: Path) -> None:
    for path in directory.glob("distribution-windows-*.json"):
        distribution = DistributionManifest.load(path)
        filename = f"LaTeXSnipper_{distribution.version}_windows_x86_64_{distribution.edition}.exe"
        source = signed / filename
        if not source.is_file():
            raise ManifestError(f"Missing signed Windows installer: {filename}")
        import shutil

        shutil.copy2(source, directory / filename)
        base_url = distribution.component("application").artifact.url.rsplit("/", 1)[0]
        distribution = replace(
            distribution, installer=artifact(directory / filename, base_url)
        )
        write_json(path, distribution.to_dict())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Complete a desktop release from build metadata"
    )
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--tag", required=True)
    arguments = parser.parse_args()
    publish_release(arguments.directory, arguments.version, arguments.tag)
