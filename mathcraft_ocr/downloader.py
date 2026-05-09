# coding: utf-8

from __future__ import annotations

import hashlib
import shutil
import socket
import tempfile
import threading
import time
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path

from .cache import model_dir
from .errors import DownloadUnavailableError, ModelCacheError
from .manifest import ModelSpec


# ---------------------------------------------------------------------------
# GitHub 加速镜像列表 — 按优先级排列
# ---------------------------------------------------------------------------
_GITHUB_MIRRORS = [
    "https://ghproxy.com/",
    "https://mirror.ghproxy.com/",
    "https://gh.api.99988866.xyz/",
    "https://gh-proxy.com/",
    "https://github.moeyy.xyz/",
]

# 用于测速的小文件 URL（GitHub 上一个很小的文件）
_SPEED_TEST_PATH = "https://raw.githubusercontent.com/SakuraMathcraft/MathCraft-Models/main/README.md"


def _is_github_url(url: str) -> bool:
    return "github.com" in url


def _expand_mirrors(source: str) -> list[str]:
    """将 GitHub URL 展开为多个镜像候选 URL（原始 URL 排在最后作为兜底）。"""
    urls: list[str] = []
    if _is_github_url(source):
        for mirror in _GITHUB_MIRRORS:
            urls.append(mirror.rstrip("/") + "/" + source)
    # 原始 URL 作为最后的兜底
    urls.append(source)
    return urls


def _test_url_speed(url: str, timeout: float = 5.0) -> float:
    """测试 URL 的响应速度，返回首字节时间（秒）。失败返回 inf。"""
    try:
        start = time.monotonic()
        req = urllib.request.Request(url, headers={"Range": "bytes=0-1023"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            _ = resp.read(1024)
        elapsed = time.monotonic() - start
        return elapsed
    except Exception:
        return float("inf")


def _select_fastest_mirrors(sources: list[str], timeout: float = 5.0) -> list[str]:
    """测速并返回按速度排序的 URL 列表（最快的在前）。"""
    if len(sources) <= 1:
        return sources

    results: list[tuple[float, str]] = []

    def _test(url: str) -> None:
        speed = _test_url_speed(url, timeout=timeout)
        results.append((speed, url))

    threads: list[threading.Thread] = []
    for url in sources:
        t = threading.Thread(target=_test, args=(url,), daemon=True)
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=timeout + 2.0)

    results.sort(key=lambda x: x[0])
    return [url for _, url in results]


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
    enable_mirrors: bool = True,
) -> Path:
    sources = list(source_overrides.get(spec.model_id, ())) if source_overrides else []
    if not sources:
        sources = list(spec.sources)

    # 展开 GitHub 镜像
    if enable_mirrors:
        expanded: list[str] = []
        for src in sources:
            if src and not _is_placeholder_source(src):
                if _is_github_url(src):
                    expanded.extend(_expand_mirrors(src))
                else:
                    expanded.append(src)
        if expanded:
            sources = expanded

    sources = [src for src in sources if src and not _is_placeholder_source(src)]
    if not sources:
        raise DownloadUnavailableError(
            f"no usable download source configured for model '{spec.model_id}'"
        )

    # 多镜像测速并择优排序（仅在启用镜像且有多个候选时）
    if enable_mirrors and len(sources) > 1:
        if progress_callback:
            progress_callback(f"model {spec.model_id} testing {len(sources)} mirrors...")
        sources = _select_fastest_mirrors(sources, timeout=5.0)
        if progress_callback:
            fastest = sources[0]
            label = "原始源" if fastest in spec.sources else "镜像"
            progress_callback(f"model {spec.model_id} selected fastest ({label}): {fastest[:80]}...")

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
