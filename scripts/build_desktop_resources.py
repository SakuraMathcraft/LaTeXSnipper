"""Assemble official, locked models and application Pandoc resources for Actions."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts"), str(ROOT / "src")]

from distribution_archives import download_artifact  # noqa: E402
from distribution_inputs import load_resources  # noqa: E402
from mathcraft_ocr.manifest import load_manifest  # noqa: E402
from runtime.component_archive import extract_archive  # noqa: E402
from runtime.component_inventory import file_sha256, inventory_component  # noqa: E402
from runtime.distribution_manifest import Artifact, ManifestError  # noqa: E402
from runtime.processes import hidden_subprocess_kwargs  # noqa: E402


def assemble_models(lock: dict, output: Path, cache: Path) -> None:
    manifest_source = download_artifact(
        Artifact.from_dict(lock["model_manifest"]), cache
    )
    manifest = load_manifest(manifest_source)
    if manifest.version != lock["model_format"] or set(manifest.models) != set(
        lock["models"]
    ):
        raise ManifestError("Official model manifest does not match the resource lock")
    output.mkdir()
    shutil.copy2(manifest_source, output / "models.v1.json")
    for model_id, spec in manifest.models.items():
        source = Artifact.from_dict(lock["models"][model_id])
        if spec.sources != (source.url,):
            raise ManifestError(
                "Official model archive does not match its manifest source"
            )
        archive = download_artifact(source, cache)
        with tempfile.TemporaryDirectory(
            prefix="model-source-", dir=output.parent
        ) as temporary:
            extracted = Path(temporary) / "extracted"
            extract_archive(archive, extracted)
            model_root = extracted / model_id
            if not model_root.is_dir():
                model_root = extracted
            destination = output / model_id
            destination.mkdir()
            for item in spec.files:
                path = model_root / item.path
                if (
                    path.is_symlink()
                    or not path.is_file()
                    or file_sha256(path) != item.sha256
                ):
                    raise ManifestError(
                        f"Official model file integrity failure: {model_id}/{item.path}"
                    )
                target = destination / item.path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
    license_source = download_artifact(
        Artifact.from_dict(lock["licenses"]["models"]), cache
    )
    shutil.copy2(license_source, output / "LICENSE")
    # Shared model data must survive artifact transfer and be readable after install.
    for path in output.rglob("*"):
        if path.is_file():
            path.chmod(0o644)


def assemble_pandoc(lock: dict, target: str, output: Path, cache: Path) -> None:
    archive = download_artifact(Artifact.from_dict(lock["pandoc"][target]), cache)
    with tempfile.TemporaryDirectory(
        prefix="pandoc-source-", dir=output.parent
    ) as temporary:
        extracted = Path(temporary) / "extracted"
        extract_archive(archive, extracted)
        name = "pandoc.exe" if target.startswith("windows") else "pandoc"
        candidates = [
            path
            for path in extracted.rglob(name)
            if path.is_file() and not path.is_symlink()
        ]
        if len(candidates) != 1:
            raise ManifestError("Official Pandoc archive needs exactly one executable")
        output.mkdir()
        shutil.copy2(candidates[0], output / name)
        (output / name).chmod(0o755)
    license_source = download_artifact(
        Artifact.from_dict(lock["licenses"]["pandoc"]), cache
    )
    shutil.copy2(license_source, output / "COPYING.md")
    (output / "COPYING.md").chmod(0o644)
    host = {"win32": "windows", "linux": "linux", "darwin": "macos"}.get(sys.platform)
    if target.split("-")[0] != host:
        raise ManifestError("Pandoc must be verified on its target platform")
    result = subprocess.run(
        [str(output / name), "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        **hidden_subprocess_kwargs(),
    )
    if (
        result.returncode
        or result.stdout.splitlines()[0] != f"pandoc {lock['pandoc_version']}"
    ):
        raise ManifestError("Assembled Pandoc version does not match its lock")


def assemble(args: argparse.Namespace) -> None:
    lock = load_resources(args.lock)
    output = args.output.resolve()
    cache = args.cache.resolve()
    if (
        output.exists()
        or output == cache
        or cache.is_relative_to(output)
        or output.is_relative_to(cache)
    ):
        raise ManifestError(
            "Build output must be fresh and separate from the download cache"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="desktop-resources-", dir=output.parent
    ) as temporary:
        staged = Path(temporary) / "payload"
        if args.resource == "models":
            assemble_models(lock, staged, cache)
        else:
            if args.target is None:
                raise ManifestError(
                    "Pandoc assembly requires an explicit platform target"
                )
            assemble_pandoc(lock, args.target, staged, cache)
        files = inventory_component(staged)
        staged.rename(output)
    print(
        json.dumps(
            {
                "resource": args.resource,
                "target": args.target,
                "file_count": len(files),
                "uncompressed_bytes": sum(item.size for item in files),
            }
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("resource", choices=("models", "pandoc"))
    parser.add_argument(
        "--target", choices=("windows-x86_64", "linux-x86_64", "macos-arm64")
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument(
        "--lock", type=Path, default=ROOT / "packaging/runtime/resources.lock.json"
    )
    assemble(parser.parse_args())


if __name__ == "__main__":
    main()
