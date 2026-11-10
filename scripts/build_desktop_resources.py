"""Assemble the official, locked models for desktop releases."""

from __future__ import annotations

import argparse
import json
import shutil
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


def assemble(output: Path, cache: Path, lock_path: Path) -> None:
    lock = load_resources(lock_path)
    output = output.resolve()
    cache = cache.resolve()
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
        assemble_models(lock, staged, cache)
        files = inventory_component(staged)
        staged.rename(output)
    print(
        json.dumps(
            {
                "resource": "models",
                "file_count": len(files),
                "uncompressed_bytes": sum(item.size for item in files),
            }
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument(
        "--lock", type=Path, default=ROOT / "packaging/runtime/resources.lock.json"
    )
    args = parser.parse_args()
    assemble(args.output, args.cache, args.lock)


if __name__ == "__main__":
    main()
