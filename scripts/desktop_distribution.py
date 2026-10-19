"""Build and inspect the component protocol used by desktop distribution."""

from __future__ import annotations

import argparse
import json
import stat
import sys
import zipfile
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

from distribution_inputs import (  # noqa: E402
    load_dependencies,
    load_resources,
    load_sources,
)
from runtime.component_inventory import (  # noqa: E402
    file_sha256,
    inventory_component,
    verify_component,
)
from runtime.distribution_manifest import (  # noqa: E402
    Artifact,
    Component,
    ManifestError,
)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def build_component(args: argparse.Namespace) -> None:
    source = args.source.resolve(strict=True)
    output = args.output.resolve()
    if output == source or output.is_relative_to(source):
        raise ManifestError("Output must be outside the component source")
    records = inventory_component(source)
    output.mkdir(parents=True, exist_ok=True)
    placeholder = Artifact(args.base_url.rstrip("/") + "/pending.zip", "0" * 64, 1)
    component = Component(
        args.name,
        args.platform,
        args.architecture,
        args.variant,
        args.worker_protocol,
        args.model_format,
        records,
        placeholder,
    )
    filename = f"{component.name}-{component.platform}-{component.architecture}-{component.variant}-{component.content_sha256}.zip"
    archive = output / filename
    try:
        with zipfile.ZipFile(
            archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
        ) as package:
            for record in records:
                entry = zipfile.ZipInfo(record.path, date_time=(1980, 1, 1, 0, 0, 0))
                entry.create_system = 3
                entry.external_attr = (
                    (stat.S_IFLNK if record.kind == "symlink" else stat.S_IFREG)
                    | record.mode
                ) << 16
                entry.compress_type = zipfile.ZIP_DEFLATED
                if record.kind == "symlink":
                    package.writestr(entry, record.target.encode("utf-8"))
                else:
                    with (
                        source.joinpath(*record.path.split("/")).open("rb") as incoming,
                        package.open(entry, "w", force_zip64=True) as outgoing,
                    ):
                        for block in iter(lambda: incoming.read(1024 * 1024), b""):
                            outgoing.write(block)
        if verify_component(source, component):
            raise ManifestError("Component source changed during packaging")
        artifact = Artifact(
            args.base_url.rstrip("/") + "/" + quote(filename),
            file_sha256(archive),
            archive.stat().st_size,
        )
        component = Component(
            args.name,
            args.platform,
            args.architecture,
            args.variant,
            args.worker_protocol,
            args.model_format,
            records,
            artifact,
        )
        metadata = output / f"{filename}.json"
        write_json(metadata, component.to_dict())
        print(
            json.dumps(
                {
                    "metadata": str(metadata),
                    "uncompressed_bytes": sum(item.size for item in records),
                    "download_bytes": artifact.size,
                }
            )
        )
    except Exception:
        archive.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    sources = commands.add_parser(
        "sources", help="Validate pinned source archives without downloading them"
    )
    sources.add_argument(
        "--catalog", type=Path, default=ROOT / "packaging/runtime/sources.lock.json"
    )
    sources.add_argument(
        "--dependency-lock",
        type=Path,
        default=ROOT / "packaging/runtime/dependencies.lock.json",
    )
    sources.add_argument(
        "--resource-lock",
        type=Path,
        default=ROOT / "packaging/runtime/resources.lock.json",
    )
    component = commands.add_parser(
        "component", help="Package an immutable component and inventory"
    )
    component.add_argument("--source", type=Path, required=True)
    component.add_argument("--output", type=Path, required=True)
    component.add_argument(
        "--name",
        choices=(
            "application",
            "runtime",
            "inference",
            "models",
            "base",
            "maintenance",
        ),
        required=True,
    )
    component.add_argument(
        "--platform", choices=("windows", "linux", "macos", "any"), required=True
    )
    component.add_argument(
        "--architecture", choices=("x86_64", "arm64", "any"), required=True
    )
    component.add_argument("--variant", choices=("common", "cpu", "gpu"), required=True)
    component.add_argument("--worker-protocol", type=int, required=True)
    component.add_argument("--model-format", type=int, required=True)
    component.add_argument("--base-url", required=True)
    args = parser.parse_args()
    if args.command == "sources":
        source_lock = load_sources(args.catalog)
        dependency_lock = load_dependencies(args.dependency_lock, source_lock)
        resource_lock = load_resources(args.resource_lock)
        print(
            json.dumps(
                {
                    "targets": sorted(source_lock["targets"]),
                    "dependencies": {
                        target: len(items)
                        for target, items in dependency_lock["targets"].items()
                    },
                    "models": sorted(resource_lock["models"]),
                    "pandoc": resource_lock["pandoc_version"],
                }
            )
        )
    elif args.command == "component":
        build_component(args)


if __name__ == "__main__":
    main()
