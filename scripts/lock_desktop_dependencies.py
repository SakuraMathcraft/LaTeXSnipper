"""Pin platform inference archives from a pip resolution report and PyPI metadata."""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.tags import compatible_tags, cpython_tags, mac_platforms
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]


def metadata(name: str, version: str | None = None) -> dict:
    suffix = f"/{version}" if version else ""
    response = requests.get(f"https://pypi.org/pypi/{name}{suffix}/json", timeout=30)
    response.raise_for_status()
    return response.json()


def artifact(item: dict) -> dict:
    return {
        "url": item["url"],
        "sha256": item["digests"]["sha256"],
        "size": item["size"],
    }


def target_tags(target: str) -> list:
    if target == "windows-x86_64":
        platforms = ["win_amd64"]
    elif target == "linux-x86_64":
        platforms = [f"manylinux_2_{minor}_x86_64" for minor in range(28, 16, -1)] + [
            "manylinux2014_x86_64"
        ]
    elif target == "macos-arm64":
        platforms = list(mac_platforms(version=(14, 0), arch="arm64"))
    else:
        raise ValueError(f"Unsupported target: {target}")
    return list(
        cpython_tags(python_version=(3, 11), abis=["cp311"], platforms=platforms)
    ) + list(
        compatible_tags(
            python_version=(3, 11), interpreter="cp311", platforms=platforms
        )
    )


def select_archive(name: str, data: dict, tags: list) -> dict:
    rank = {tag: index for index, tag in enumerate(tags)}
    candidates = []
    for item in data["urls"]:
        if item["yanked"] or item["packagetype"] != "bdist_wheel":
            continue
        _, _, _, wheel_tags = parse_wheel_filename(item["filename"])
        matches = [rank[tag] for tag in wheel_tags if tag in rank]
        if matches:
            candidates.append((min(matches), item["filename"], item))
    if candidates:
        selected = min(candidates, key=lambda item: item[:2])[2]
        return {
            "name": name,
            "version": data["info"]["version"],
            "kind": "wheel",
            "artifact": artifact(selected),
        }
    if name != "antlr4-python3-runtime":
        raise ValueError(
            f"No compatible binary wheel: {name}=={data['info']['version']}"
        )
    sources = [
        item
        for item in data["urls"]
        if item["packagetype"] == "sdist" and not item["yanked"]
    ]
    if len(sources) != 1:
        raise ValueError("Expected one pinned ANTLR source archive")
    return {
        "name": name,
        "version": data["info"]["version"],
        "kind": "sdist",
        "artifact": artifact(sources[0]),
    }


def environment(target: str, python_version: str) -> dict:
    result = {key: str(value) for key, value in default_environment().items()}
    result.update(
        python_version="3.11",
        python_full_version=python_version,
        implementation_name="cpython",
        implementation_version=python_version,
        platform_python_implementation="CPython",
        extra="",
    )
    platform, _ = target.split("-", 1)
    result.update(
        os_name="nt" if platform == "windows" else "posix",
        sys_platform={"windows": "win32", "linux": "linux", "macos": "darwin"}[
            platform
        ],
        platform_system={"windows": "Windows", "linux": "Linux", "macos": "Darwin"}[
            platform
        ],
        platform_machine={"windows": "AMD64", "linux": "x86_64", "macos": "arm64"}[
            platform
        ],
    )
    return result


def lock_dependencies(report: Path, inputs: Path, catalog: Path, output: Path) -> None:
    resolved = json.loads(report.read_text(encoding="utf-8"))
    sources = json.loads(catalog.read_text(encoding="utf-8"))
    pins = {
        canonicalize_name(item["metadata"]["name"]): item["metadata"]["version"]
        for item in resolved["install"]
    }
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {
            name: pool.submit(metadata, name, version) for name, version in pins.items()
        }
        packages = {name: future.result() for name, future in futures.items()}
    roots = [
        Requirement(line)
        for line in inputs.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    targets = {}
    for target in sources["targets"]:
        env = environment(target, sources["python_version"])
        requirements = list(roots)
        visited = set()
        while requirements:
            requirement = requirements.pop()
            if requirement.marker and not requirement.marker.evaluate(env):
                continue
            name = canonicalize_name(requirement.name)
            if name not in packages:
                latest = metadata(name)
                versions = sorted(
                    (
                        Version(version)
                        for version in latest["releases"]
                        if not Version(version).is_prerelease
                        and Version(version) in requirement.specifier
                    ),
                    reverse=True,
                )
                if not versions:
                    raise ValueError(f"No release satisfies {requirement}")
                packages[name] = metadata(name, str(versions[0]))
            data = packages[name]
            if Version(data["info"]["version"]) not in requirement.specifier:
                raise ValueError(
                    f"Pinned dependency violates {requirement}: {data['info']['version']}"
                )
            python_spec = data["info"].get("requires_python")
            if python_spec:
                from packaging.specifiers import SpecifierSet

                if Version(sources["python_version"]) not in SpecifierSet(python_spec):
                    raise ValueError(f"Python version mismatch: {name}")
            if name in visited:
                continue
            visited.add(name)
            requirements.extend(
                Requirement(value)
                for value in (data["info"].get("requires_dist") or [])
            )
        visited.discard("onnxruntime")
        tags = target_tags(target)
        targets[target] = [
            select_archive(name, packages[name], tags) for name in sorted(visited)
        ]
    build_tools = []
    for name in ("pip", "setuptools", "wheel"):
        data = metadata(name)
        if name == "setuptools":
            versions = sorted(
                (
                    Version(version)
                    for version in data["releases"]
                    if not Version(version).is_prerelease
                    and Version(version) < Version("82")
                ),
                reverse=True,
            )
            data = metadata(name, str(versions[0]))
        build_tools.append(select_archive(name, data, target_tags("windows-x86_64")))
    result = {
        "schema": 1,
        "python_version": sources["python_version"],
        "requirements": [str(item) for item in roots],
        "build_tools": build_tools,
        "targets": targets,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    for target, entries in targets.items():
        print(
            f"{target}: {len(entries)} locked dependencies; {sum(item['artifact']['size'] for item in entries)} source bytes"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--inputs", type=Path, default=ROOT / "packaging/runtime/requirements.in"
    )
    parser.add_argument(
        "--catalog", type=Path, default=ROOT / "packaging/runtime/sources.lock.json"
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "packaging/runtime/dependencies.lock.json"
    )
    args = parser.parse_args()
    lock_dependencies(args.report, args.inputs, args.catalog, args.output)


if __name__ == "__main__":
    main()
