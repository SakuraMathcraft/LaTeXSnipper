# coding: utf-8

from __future__ import annotations

import hashlib
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from .cache import model_dir
from .errors import DownloadUnavailableError, ModelCacheError
from .manifest import ModelSpec


def _is_placeholder_source(source: str) -> bool:
    return source.startswith("placeholder://") or source.endswith(".invalid")


def _sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _verify_model_dir(target: Path, spec: ModelSpec) -> None:
    for file_spec in spec.files:
        fp = target / file_spec.path
        if not fp.is_file():
            raise ModelCacheError(f"required file missing for {spec.model_id}: {file_spec.path}")
        if file_spec.sha256:
            actual = _sha256_of_file(fp)
            if actual.lower() != file_spec.sha256.lower():
                raise ModelCacheError(
                    f"sha256 mismatch for {spec.model_id}: {file_spec.path}"
                )


def download_model_archive(
    spec: ModelSpec,
    *,
    target_root: str | Path,
    timeout: int = 60,
    source_overrides: dict[str, list[str] | tuple[str, ...]] | None = None,
) -> Path:
    sources = list(source_overrides.get(spec.model_id, ())) if source_overrides else []
    if not sources:
        sources = list(spec.sources)
    sources = [src for src in sources if src and not _is_placeholder_source(src)]
    if not sources:
        raise DownloadUnavailableError(
            f"no usable download source configured for model '{spec.model_id}'"
        )

    target_root = Path(target_root)
    target_root.mkdir(parents=True, exist_ok=True)
    final_dir = model_dir(target_root, spec.model_id)
    last_error: Exception | None = None

    for source in sources:
        temp_dir = Path(tempfile.mkdtemp(prefix=f"mathcraft-{spec.model_id}-"))
        archive_path = temp_dir / "payload.zip"
        extract_dir = temp_dir / "extract"
        try:
            with urllib.request.urlopen(source, timeout=timeout) as response:
                archive_path.write_bytes(response.read())
            extract_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(extract_dir)
            extracted_root = extract_dir / spec.model_id
            if not extracted_root.is_dir():
                extracted_root = extract_dir
            _verify_model_dir(extracted_root, spec)
            backup_dir = None
            if final_dir.exists():
                backup_dir = final_dir.with_name(final_dir.name + ".bak")
                if backup_dir.exists():
                    shutil.rmtree(backup_dir, ignore_errors=True)
                final_dir.replace(backup_dir)
            shutil.move(str(extracted_root), str(final_dir))
            if backup_dir and backup_dir.exists():
                shutil.rmtree(backup_dir, ignore_errors=True)
            return final_dir
        except Exception as exc:
            last_error = exc
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    raise ModelCacheError(
        f"failed to download model '{spec.model_id}': {last_error}"
    ) from last_error
