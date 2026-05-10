# coding: utf-8

from __future__ import annotations

import hashlib
import shutil
import tempfile
import time
import urllib.request
import zipfile
from collections.abc import Callable
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


def _content_length(headers) -> int:
    try:
        return int(headers.get("Content-Length") or 0)
    except (TypeError, ValueError):
        return 0


def _content_range_total(headers) -> int:
    value = headers.get("Content-Range") or ""
    if "/" not in value:
        return 0
    total = value.rsplit("/", 1)[-1].strip()
    if not total or total == "*":
        return 0
    try:
        return int(total)
    except ValueError:
        return 0


def _download_archive_file(
    source: str,
    archive_path: Path,
    spec: ModelSpec,
    *,
    timeout: float | None,
    progress_callback: Callable[[str], None] | None,
) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    existing_size = archive_path.stat().st_size if archive_path.is_file() else 0
    headers = {"Range": f"bytes={existing_size}-"} if existing_size > 0 else {}
    if progress_callback:
        if existing_size > 0:
            progress_callback(
                f"model {spec.model_id} resuming archive from {existing_size / 1048576:.1f} MB"
            )
        else:
            progress_callback(f"model {spec.model_id} downloading archive")

    request = urllib.request.Request(source, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        status = int(getattr(response, "status", 200) or 200)
        content_length = _content_length(response.headers)
        content_range_total = _content_range_total(response.headers)
        can_resume = existing_size > 0 and status == 206
        if existing_size > 0 and not can_resume and progress_callback:
            progress_callback(
                f"model {spec.model_id} server did not resume, restarting archive download"
            )
        total = content_range_total if can_resume else content_length
        downloaded = existing_size if can_resume else 0
        mode = "ab" if can_resume else "wb"
        last_report_time = 0.0
        last_report_percent = max(-10, int(downloaded * 100 / total) - 10) if total > 0 else -10
        with archive_path.open(mode) as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                downloaded += len(chunk)
                if not progress_callback:
                    continue
                now = time.monotonic()
                if total > 0:
                    percent = int(downloaded * 100 / total)
                    should_report = (
                        percent >= last_report_percent + 10
                        or downloaded >= total
                        or now - last_report_time >= 5.0
                    )
                    if should_report:
                        progress_callback(
                            f"model {spec.model_id} download {percent}% "
                            f"({downloaded / 1048576:.1f}/{total / 1048576:.1f} MB)"
                        )
                        last_report_percent = percent
                        last_report_time = now
                elif now - last_report_time >= 5.0:
                    progress_callback(
                        f"model {spec.model_id} download {downloaded / 1048576:.1f} MB"
                    )
                    last_report_time = now

    if total > 0 and downloaded < total:
        raise ModelCacheError(
            f"incomplete download for {spec.model_id}: "
            f"{downloaded / 1048576:.1f}/{total / 1048576:.1f} MB; partial saved"
        )


def download_model_archive(
    spec: ModelSpec,
    *,
    target_root: str | Path,
    timeout: float | None = None,
    source_overrides: dict[str, list[str] | tuple[str, ...]] | None = None,
    progress_callback: Callable[[str], None] | None = None,
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
    downloads_dir = target_root / ".downloads"
    archive_path = downloads_dir / f"{spec.model_id}.zip.part"
    last_error: Exception | None = None

    for source in sources:
        temp_dir = Path(tempfile.mkdtemp(prefix=f"mathcraft-{spec.model_id}-"))
        extract_dir = temp_dir / "extract"
        try:
            _download_archive_file(
                source,
                archive_path,
                spec,
                timeout=timeout,
                progress_callback=progress_callback,
            )
            extract_dir.mkdir(parents=True, exist_ok=True)
            if progress_callback:
                progress_callback(f"model {spec.model_id} verifying archive")
            try:
                with zipfile.ZipFile(archive_path, "r") as zf:
                    zf.extractall(extract_dir)
            except zipfile.BadZipFile as exc:
                archive_path.unlink(missing_ok=True)
                raise ModelCacheError(
                    f"downloaded archive for {spec.model_id} is corrupt; partial removed"
                ) from exc
            extracted_root = extract_dir / spec.model_id
            if not extracted_root.is_dir():
                extracted_root = extract_dir
            try:
                _verify_model_dir(extracted_root, spec)
            except ModelCacheError:
                archive_path.unlink(missing_ok=True)
                raise
            backup_dir = None
            if final_dir.exists():
                backup_dir = final_dir.with_name(final_dir.name + ".bak")
                if backup_dir.exists():
                    shutil.rmtree(backup_dir, ignore_errors=True)
                final_dir.replace(backup_dir)
            shutil.move(str(extracted_root), str(final_dir))
            if backup_dir and backup_dir.exists():
                shutil.rmtree(backup_dir, ignore_errors=True)
            archive_path.unlink(missing_ok=True)
            return final_dir
        except Exception as exc:
            last_error = exc
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    raise ModelCacheError(
        f"failed to download model '{spec.model_id}': {last_error}"
    ) from last_error
