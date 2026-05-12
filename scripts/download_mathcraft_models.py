#!/usr/bin/env python3
"""Download and verify MathCraft model archives for offline packaging.

Reads the model manifest, downloads archives from GitHub Releases,
extracts them, and verifies SHA256 checksums of every model file.

Exit codes:
    0 - All models present and verified
    1 - Download or verification failed

Usage:
    python3 scripts/download_mathcraft_models.py <target_dir>

The <target_dir> will contain one subdirectory per model (e.g.
<target_dir>/mathcraft-formula-det/...).
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

MANIFEST_REL = "mathcraft_ocr/manifests/models.v1.json"
CHUNK_SIZE = 1024 * 1024  # 1 MiB


def sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def verify_model_dir(model_dir: Path, files: list[dict[str, str]]) -> bool:
    """Return True if all expected files exist and SHA256 matches."""
    for entry in files:
        fp = model_dir / entry["path"]
        if not fp.is_file():
            return False
        expected = entry.get("sha256", "")
        if expected:
            actual = sha256_of_file(fp)
            if actual.lower() != expected.lower():
                return False
    return True


def download_archive(url: str, dest: Path, model_id: str) -> None:
    """Download a file from *url* to *dest* with basic progress output."""
    print(f"  Downloading {model_id} from {url}")
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=300) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        downloaded = 0
        with dest.open("wb") as out:
            while True:
                chunk = resp.read(CHUNK_SIZE)
                if not chunk:
                    break
                out.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    pct = downloaded * 100 // total
                    print(
                        f"\r  {model_id}: {pct}% ({downloaded // (1024*1024)}"
                        f"/{total // (1024*1024)} MiB)",
                        end="",
                        flush=True,
                    )
        if total > 0:
            print()  # newline after progress


def download_and_extract(
    model_id: str,
    spec: dict,
    target_dir: Path,
) -> bool:
    """Download a model archive, extract, and verify.

    Returns True on success.
    """
    sources: list[str] = spec.get("sources", [])
    files: list[dict[str, str]] = spec.get("files", [])
    model_dir = target_dir / model_id

    # Skip if already present and verified.
    if model_dir.is_dir() and verify_model_dir(model_dir, files):
        print(f"  {model_id}: already present and verified, skipping")
        return True

    usable_sources = [
        s for s in sources
        if s and not s.startswith("placeholder://") and not s.endswith(".invalid")
    ]
    if not usable_sources:
        print(f"  ERROR: {model_id}: no usable download source", file=sys.stderr)
        return False

    last_error: Exception | None = None
    for source in usable_sources:
        try:
            with tempfile.TemporaryDirectory(prefix=f"mathcraft-{model_id}-") as td:
                archive = Path(td) / f"{model_id}.zip"
                download_archive(source, archive, model_id)

                print(f"  Extracting {model_id}")
                extract_dir = Path(td) / "extract"
                extract_dir.mkdir()
                with zipfile.ZipFile(archive) as zf:
                    zf.extractall(extract_dir)

                # The archive may contain a top-level directory matching the
                # model_id, or files directly at the root.
                extracted = extract_dir / model_id
                if not extracted.is_dir():
                    extracted = extract_dir

                # Move into final location.
                if model_dir.exists():
                    shutil.rmtree(model_dir)
                shutil.move(str(extracted), str(model_dir))

            # Verify after extraction.
            if not verify_model_dir(model_dir, files):
                print(
                    f"  ERROR: {model_id}: SHA256 verification failed after extraction",
                    file=sys.stderr,
                )
                shutil.rmtree(model_dir, ignore_errors=True)
                return False

            print(f"  {model_id}: downloaded and verified")
            return True
        except Exception as exc:
            last_error = exc
            print(f"  {model_id}: attempt failed: {exc}", file=sys.stderr)

    print(
        f"  ERROR: {model_id}: all download sources exhausted: {last_error}",
        file=sys.stderr,
    )
    return False


def main() -> int:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <target_dir>", file=sys.stderr)
        return 1

    project_root = Path(__file__).resolve().parent.parent
    manifest_path = project_root / MANIFEST_REL
    target_dir = Path(sys.argv[1]).resolve()

    if not manifest_path.is_file():
        print(f"ERROR: manifest not found: {manifest_path}", file=sys.stderr)
        return 1

    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    models: dict[str, dict] = manifest.get("models", {})
    if not models:
        print("ERROR: manifest contains no models", file=sys.stderr)
        return 1

    target_dir.mkdir(parents=True, exist_ok=True)
    print(f"Target directory: {target_dir}")
    print(f"Models to process: {len(models)}")

    failures = 0
    for model_id, spec in models.items():
        print(f"[{model_id}]")
        if not download_and_extract(model_id, spec, target_dir):
            failures += 1

    if failures:
        print(f"\nERROR: {failures} model(s) failed", file=sys.stderr)
        return 1

    print(f"\nAll {len(models)} models ready at {target_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
