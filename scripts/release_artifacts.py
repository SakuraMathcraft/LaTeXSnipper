"""Package and publish immutable desktop resources."""

import argparse
import json
import os
import re
import subprocess
import sys
from argparse import Namespace
from dataclasses import replace
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

from desktop_distribution import build_component, write_json  # noqa: E402
from runtime.component_inventory import file_sha256  # noqa: E402
from runtime.distribution_manifest import (  # noqa: E402
    Artifact,
    Component,
    DistributionManifest,
    ManifestError,
    ReleaseCatalog,
    read_json,
)

RELEASES = "repos/{owner}/{repo}/releases"


def github_api(endpoint: str, *, method="GET", data=None, file=None, paginate=False):
    command = ["gh", "api", "--method", method, endpoint]
    if paginate:
        command += ["--paginate", "--slurp"]
    if file is not None:
        command += [
            "--header",
            "Content-Type: application/octet-stream",
            "--input",
            str(file),
        ]
    elif data is not None:
        command += ["--input", "-"]
    result = subprocess.check_output(
        command,
        input=json.dumps(data) if data is not None else None,
        encoding="utf-8",
    )
    return json.loads(result) if result.strip() else {}


def prepare_release(tag: str, target: str) -> int:
    pages = github_api(f"{RELEASES}?per_page=100", paginate=True)
    matches = [
        item
        for page in pages
        for item in page
        if item["tag_name"] == tag and not item["draft"]
    ]
    if len(matches) > 1:
        raise ManifestError(f"Multiple published releases have tag {tag}")
    if matches:
        return matches[0]["id"]
    return github_api(
        RELEASES,
        method="POST",
        data={
            "tag_name": tag,
            "target_commitish": target,
            "name": tag,
            "draft": False,
            "generate_release_notes": True,
        },
    )["id"]


def upload_assets(release_id: int, paths: list[Path]) -> None:
    release = github_api(f"{RELEASES}/{release_id}")
    existing = {asset["name"]: asset for asset in release["assets"]}
    upload_url = release["upload_url"].split("{", 1)[0]
    for path in paths:
        if path.stat().st_size >= 2**31:
            raise ManifestError(
                f"Release asset exceeds GitHub's 2 GiB limit: {path.name}"
            )
        if path.name in existing:
            github_api(
                f"{RELEASES}/assets/{existing[path.name]['id']}", method="DELETE"
            )
        github_api(
            f"{upload_url}?name={quote(path.name, safe='')}", method="POST", file=path
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
    return component


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


def publish_release(directory: Path, version: str, tag: str, release_id: int) -> None:
    catalog_path = directory / "desktop-release.json"
    catalog = publish_catalog(directory, version, catalog_path)
    names = {
        catalog_path.name,
        f"LaTeXSnipperOffice_{version}_amd64.exe",
        "LaTeXSnipper_User_Manual.pdf",
    }
    for distribution in catalog.distributions:
        resources = [distribution.application.artifact]
        if distribution.installer is None:
            raise ManifestError("Release is missing its installer")
        resources.append(distribution.installer)
        names.update(resource.url.rsplit("/", 1)[-1] for resource in resources)
    release = github_api(f"{RELEASES}/{release_id}")
    if release["tag_name"] != tag or release["draft"]:
        raise ManifestError("Release ID must match the requested published release")
    upload_assets(release_id, [catalog_path])
    assets = github_api(f"{RELEASES}/{release_id}")["assets"]
    missing = names - {
        asset["name"] for asset in assets if asset["state"] == "uploaded"
    }
    if missing:
        raise ManifestError(
            f"Release is missing uploaded assets: {', '.join(sorted(missing))}"
        )
    for asset in assets:
        if asset["name"] not in names:
            github_api(f"{RELEASES}/assets/{asset['id']}", method="DELETE")


def prune_build_cache(directory: Path) -> None:
    """Retain the exact inputs recorded by all three successful platform builds."""
    from desktop_base_cache import cache_tag

    targets = {"windows-x86_64", "linux-x86_64", "macos-arm64"}
    seen: set[str] = set()
    keep: set[str] = set()
    for path in sorted(directory.glob("cache-plan-*.json")):
        plan = read_json(path)
        target = plan["target"]
        if plan["schema"] != 1 or target not in targets or target in seen:
            raise ManifestError("Invalid platform build-cache plan")
        seen.add(target)
        required = {"runtime", "inference-cpu", "models", "maintenance"}
        required |= {"base"} if target.startswith("macos-") else {"inference-gpu"}
        if set(plan["keys"]) != required:
            raise ManifestError("Incomplete platform build-cache inputs")
        for name, key in plan["keys"].items():
            if not isinstance(key, str) or not re.fullmatch(r"[0-9a-f]{64}", key):
                raise ManifestError("Invalid build-cache input identity")
            keep.add(cache_tag(name, "any-any" if name == "models" else target, key))
    if seen != targets:
        raise ManifestError("Build-cache cleanup requires all three platform plans")
    pattern = re.compile(
        r"desktop-base-(?:windows-x86_64|linux-x86_64|macos-arm64|any-any)-"
        r"(?:runtime|maintenance|models|inference-cpu|inference-gpu|base)-[0-9a-f]{64}"
    )
    for page in github_api(f"{RELEASES}?per_page=100", paginate=True):
        for release in page:
            tag = release["tag_name"]
            if release["draft"] and pattern.fullmatch(tag) and tag not in keep:
                github_api(f"{RELEASES}/{release['id']}", method="DELETE")
                print(f"Removed obsolete build-cache draft: {tag}")


def upload_desktop_assets(directory: Path, release_id: int) -> None:
    from urllib.parse import unquote, urlsplit

    resources = set()
    for path in directory.glob("distribution-*.json"):
        distribution = DistributionManifest.load(path)
        if distribution.installer is None:
            raise ManifestError("Release is missing its installer")
        resources.add(distribution.installer)
        resources.add(distribution.application.artifact)
    paths = [
        directory / unquote(urlsplit(resource.url).path.rsplit("/", 1)[-1])
        for resource in sorted(resources, key=lambda item: item.url)
    ]
    if not paths:
        raise ManifestError("No desktop release assets")
    upload_assets(release_id, paths)


def finalize_windows(directory: Path, signed: Path) -> None:
    for path in directory.glob("distribution-windows-*.json"):
        distribution = DistributionManifest.load(path)
        filename = f"LaTeXSnipper_{distribution.version}_windows_x86_64_{distribution.edition}.exe"
        source = signed / filename
        if not source.is_file():
            raise ManifestError(f"Missing signed Windows installer: {filename}")
        import shutil

        shutil.copy2(source, directory / filename)
        base_url = distribution.application.artifact.url.rsplit("/", 1)[0]
        distribution = replace(
            distribution, installer=artifact(directory / filename, base_url)
        )
        write_json(path, distribution.to_dict())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Prepare, upload and publish one desktop release"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--tag", required=True)
    prepare.add_argument("--target", required=True)
    upload = commands.add_parser("upload")
    upload.add_argument("--release-id", type=int, required=True)
    upload.add_argument("files", nargs="+", type=Path)
    publish = commands.add_parser("publish")
    publish.add_argument("--directory", type=Path, required=True)
    publish.add_argument("--version", required=True)
    publish.add_argument("--tag", required=True)
    publish.add_argument("--release-id", type=int, required=True)
    prune = commands.add_parser("prune-cache")
    prune.add_argument("--directory", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.command == "prepare":
        release_id = prepare_release(arguments.tag, arguments.target)
        print(f"release_id={release_id}")
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
                output.write(f"release_id={release_id}\n")
    elif arguments.command == "upload":
        upload_assets(arguments.release_id, arguments.files)
    elif arguments.command == "prune-cache":
        prune_build_cache(arguments.directory)
    else:
        publish_release(
            arguments.directory, arguments.version, arguments.tag, arguments.release_id
        )
