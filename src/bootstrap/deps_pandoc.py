import os
import subprocess
import sys
from pathlib import Path

from bootstrap.deps_context import flags


def _ensure_pandoc_binary(pyexe: str, log_fn=None, progress_fn=None) -> bool:
    """Ensure the pandoc executable is available."""
    if log_fn:
        log_fn("[PANDOC] 正在检查 pandoc 二进制文件...")


    import shutil as _shutil

    def _resolve_pandoc_exe() -> str | None:
        """Return the persisted or dependency-managed pandoc executable path first."""
        try:
            from runtime.pandoc_runtime import load_configured_pandoc_path
            configured = load_configured_pandoc_path()
            if configured is not None:
                return str(configured)
        except Exception:
            pass
        deps_dir = Path.cwd() / "deps" / "pandoc"
        if deps_dir.is_dir():
            for name in ("pandoc.exe", "pandoc"):
                p = deps_dir / name
                if p.exists() and p.is_file():
                    return str(p)
        return _shutil.which("pandoc")

    pandoc_exe = _resolve_pandoc_exe()
    if pandoc_exe:
        current_ver = _get_pandoc_version(pandoc_exe)
        if current_ver and not _pandoc_version_too_old(current_ver, _PANDOC_VERSION):
            if log_fn:
                log_fn(f"[PANDOC] pandoc 已就绪 (v{'.'.join(str(x) for x in current_ver)})，跳过下载 ✅")
            try:
                from runtime.pandoc_runtime import save_configured_pandoc_path
                save_configured_pandoc_path(pandoc_exe)
            except Exception:
                pass
            _cleanup_pandoc_leftovers(log_fn)
            return True
        if log_fn:
            if current_ver:
                log_fn(f"[PANDOC] 检测到 pandoc v{'.'.join(str(x) for x in current_ver)} < v{_PANDOC_VERSION}，尝试更新...")
            else:
                log_fn("[PANDOC] 检测到 pandoc 但无法读取版本，尝试更新...")


    _cleanup_pandoc_leftovers(log_fn)
    if log_fn:
        log_fn("[PANDOC] 从镜像下载 pandoc 二进制...")
    if progress_fn:
        progress_fn(85)
    ok = _download_pandoc_from_mirrors(log_fn)
    if ok:
        if log_fn:
            log_fn("[PANDOC] pandoc 二进制文件就绪 ✅")
        if progress_fn:
            progress_fn(100)
        _cleanup_pandoc_leftovers(log_fn)
        return True

    if log_fn:
        log_fn("[PANDOC] pandoc 二进制文件下载失败")
        log_fn("[PANDOC] 请手动安装：https://github.com/jgm/pandoc/releases")
        if sys.platform == "win32":
            log_fn("[PANDOC] 或运行: winget install JohnMacFarlane.Pandoc")
        elif sys.platform == "linux":
            log_fn("[PANDOC] 或运行: sudo apt install pandoc / sudo dnf install pandoc")
        elif sys.platform == "darwin":
            log_fn("[PANDOC] 或运行: brew install pandoc")
    if progress_fn:
        progress_fn(100)
    return False


def _cleanup_pandoc_leftovers(log_fn=None) -> None:
    """Clean stale pandoc binaries that do not belong to the current platform."""
    import time as _time

    removed_count = 0

    def _safe_unlink(filepath: Path, label: str) -> bool:
        """Delete a file safely with retries and delayed-delete fallback on Windows."""
        nonlocal removed_count
        for attempt in range(3):
            try:
                filepath.unlink()
                removed_count += 1
                if log_fn:
                    log_fn(f"[PANDOC] 已清理{label}: {filepath.name}")
                return True
            except PermissionError:
                if attempt < 2:
                    _time.sleep(0.5)
                    continue

                if sys.platform == "win32":
                    try:
                        import ctypes
                        ctypes.windll.kernel32.MoveFileExW(
                            str(filepath), None, 4  # MOVEFILE_DELAY_UNTIL_REBOOT = 4
                        )
                        removed_count += 1
                        if log_fn:
                            log_fn(f"[PANDOC] 已标记重启后删除{label}: {filepath.name}")
                        return True
                    except Exception:
                        pass
                if log_fn:
                    log_fn(f"[PANDOC] 清理{label}失败(占用): {filepath.name}")
                return False
            except Exception as e:
                if log_fn:
                    log_fn(f"[PANDOC] 清理{label}失败: {filepath.name} ({e})")
                return False
        return False


    pandoc_dir = _pandoc_data_dir()
    if pandoc_dir.is_dir():
        try:
            _bin_name = _pandoc_platform_archive()[1]
        except Exception:
            _bin_name = None
        for stale in pandoc_dir.iterdir():
            if stale.is_file() and stale.name.startswith("pandoc"):
                if _bin_name and stale.name == _bin_name:
                    continue
                _safe_unlink(stale, "旧二进制")

    if removed_count > 0 and log_fn:
        log_fn(f"[PANDOC] 共清理 {removed_count} 个无用文件")


def _get_pandoc_version(pandoc_path: str | None = None) -> tuple[int, ...] | None:
    """Return the installed pandoc version."""
    import shutil as _shutil
    exe = pandoc_path or _shutil.which("pandoc")
    if not exe:

        try:
            deps_dir = Path.cwd() / "deps" / "pandoc"
            for candidate in ("pandoc.exe", "pandoc"):
                cand_path = deps_dir / candidate
                if cand_path.exists():
                    exe = str(cand_path)
                    break
        except Exception:
            pass
    if not exe:
        return None

    try:
        result = subprocess.run(
            [str(exe), "--version"],
            capture_output=True, text=True, timeout=10,
            creationflags=flags if sys.platform == "win32" else 0,
        )
        if result.returncode != 0:
            return None

        first_line = (result.stdout or "").splitlines()[0].strip()
        parts = first_line.split()
        for part in parts:
            stripped = part.strip().rstrip(",")
            if stripped and stripped[0].isdigit():
                return tuple(int(x) for x in stripped.split("."))
    except Exception:
        pass
    return None


def _pandoc_version_too_old(current: tuple[int, ...] | None, target: str) -> bool:
    """Return whether the current pandoc version is older than the target version."""
    if current is None:
        return True
    target_tuple = tuple(int(x) for x in target.split("."))
    return current < target_tuple


_PANDOC_VERSION = "3.9.0.2"


def _pandoc_platform_archive() -> tuple[str, str, str]:
    """Return the archive filename, binary name, and archive type for this platform."""
    import platform as _plt
    system = _plt.system()
    machine = _plt.machine()

    if system == "Windows" and machine in ("AMD64", "x86_64"):
        return (
            f"pandoc-{_PANDOC_VERSION}-windows-x86_64.zip",
            "pandoc.exe",
            "zip",
        )
    if system == "Linux" and machine in ("x86_64", "AMD64"):
        return (
            f"pandoc-{_PANDOC_VERSION}-linux-amd64.tar.gz",
            "pandoc",
            "tar.gz",
        )
    if system == "Darwin":
        if machine == "arm64":
            return (
                f"pandoc-{_PANDOC_VERSION}-arm64-macOS.zip",
                "pandoc",
                "zip",
            )
        if machine in ("x86_64", "AMD64"):
            return (
                f"pandoc-{_PANDOC_VERSION}-x86_64-macOS.zip",
                "pandoc",
                "zip",
            )

    raise RuntimeError(
        f"[PANDOC] 不支持的平台: {system} {machine}，请手动安装 pandoc"
    )


def _build_pandoc_mirrors() -> list[str]:
    """Build pandoc mirror URLs for the current platform."""
    archive_name, _bin_name, _arc_type = _pandoc_platform_archive()
    return [

        f"https://ghfast.top/https://github.com/jgm/pandoc/releases/download/{_PANDOC_VERSION}/{archive_name}",
        f"https://gh-proxy.com/https://github.com/jgm/pandoc/releases/download/{_PANDOC_VERSION}/{archive_name}",

        f"https://github.com/jgm/pandoc/releases/download/{_PANDOC_VERSION}/{archive_name}",
    ]


def _rank_mirrors_by_speed(mirrors: list[str], log_fn=None) -> list[str]:
    """Rank mirrors by HEAD request latency."""
    import urllib.request
    import time as _time

    results: list[tuple[float, str]] = []
    for url in mirrors:
        short = url[:70]
        try:
            req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "LaTeXSnipper"})
            t0 = _time.monotonic()
            resp = urllib.request.urlopen(req, timeout=8)
            resp.close()
            latency = _time.monotonic() - t0
            results.append((latency, url))
            if log_fn:
                log_fn(f"[PANDOC] 延迟测试 {short}... → {latency:.1f}s")
        except Exception as e:
            if log_fn:
                log_fn(f"[PANDOC] 延迟测试 {short}... → 失败 ({str(e)[:60]})")
            continue

    if not results:
        return mirrors

    results.sort(key=lambda x: x[0])
    ranked = [url for _, url in results]
    if log_fn:
        log_fn(f"[PANDOC] 最快镜像: {ranked[0][:70]}...")
    return ranked


def _download_pandoc_from_mirrors(log_fn=None) -> bool:
    """Download pandoc from mirrors and extract it into deps/pandoc."""
    import urllib.request
    import time as _time

    try:
        archive_name, binary_name, archive_type = _pandoc_platform_archive()
    except RuntimeError as e:
        if log_fn:
            log_fn(f"[PANDOC] {e}")
        return False

    pandoc_dir = _pandoc_data_dir()
    pandoc_dir.mkdir(parents=True, exist_ok=True)

    mirrors = _build_pandoc_mirrors()
    if log_fn:
        log_fn(f"[PANDOC] 平台归档: {archive_name} ({archive_type})")
        log_fn(f"[PANDOC] 共 {len(mirrors)} 个镜像源，正在测速选择最快...")


    mirrors = _rank_mirrors_by_speed(mirrors, log_fn)

    for idx, url in enumerate(mirrors, start=1):
        if log_fn:
            log_fn(f"[PANDOC] [{idx}/{len(mirrors)}] 尝试: {url[:80]}...")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "LaTeXSnipper"})
            resp = urllib.request.urlopen(req, timeout=30)
            total = int(resp.headers.get("Content-Length", 0))
            if log_fn and total > 0:
                log_fn(f"[PANDOC] 文件大小: {total // 1024} KB")


            chunks: list[bytes] = []
            downloaded = 0
            last_log_time = _time.monotonic()
            last_log_bytes = 0
            chunk_size = 64 * 1024  # 64 KB

            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                chunks.append(chunk)
                downloaded += len(chunk)

                now = _time.monotonic()
                elapsed = now - last_log_time
                if elapsed >= 2.0:
                    speed = (downloaded - last_log_bytes) / elapsed / 1024  # KB/s
                    if total > 0:
                        pct = downloaded * 100 // total
                        if log_fn:
                            log_fn(f"[PANDOC] 下载中: {pct}%  ({downloaded // 1024}/{total // 1024} KB)  {speed:.0f} KB/s")
                    else:
                        if log_fn:
                            log_fn(f"[PANDOC] 下载中: {downloaded // 1024} KB  {speed:.0f} KB/s")
                    last_log_time = now
                    last_log_bytes = downloaded

            resp.close()
            data = b"".join(chunks)

            if len(data) < 100_000:
                if log_fn:
                    log_fn(f"[PANDOC] 响应过小 ({len(data)} bytes)，跳过此镜像")
                continue

            if log_fn:
                log_fn(f"[PANDOC] 下载完成 ({len(data) // 1024} KB)，正在解压 ({archive_type})...")


            exe_data = _extract_pandoc_binary(data, archive_type, binary_name, log_fn)
            if exe_data is None:
                if log_fn:
                    log_fn(f"[PANDOC] 归档中未找到 {binary_name}")
                continue

            exe_path = pandoc_dir / binary_name
            exe_path.write_bytes(exe_data)
            if log_fn:
                log_fn(f"[PANDOC] 已写入: {exe_path}")


            if sys.platform != "win32":
                try:
                    os.chmod(str(exe_path), 0o755)
                except Exception:
                    pass


            dir_str = str(pandoc_dir)
            if dir_str not in os.environ.get("PATH", ""):
                os.environ["PATH"] = dir_str + os.pathsep + os.environ.get("PATH", "")


            verify_cmd = [str(exe_path), "--version"]
            result = subprocess.run(
                verify_cmd,
                capture_output=True, text=True, timeout=10,
                creationflags=flags if sys.platform == "win32" else 0,
            )
            if result.returncode == 0:
                ver_line = (result.stdout or "").splitlines()[0]
                try:
                    from runtime.pandoc_runtime import save_configured_pandoc_path
                    save_configured_pandoc_path(exe_path)
                except Exception:
                    pass
                if log_fn:
                    log_fn(f"[PANDOC] 验证通过: {ver_line}")
                return True

        except Exception as e:
            if log_fn:
                log_fn(f"[PANDOC] 失败: {str(e)[:120]}")
            continue

    return False


def _extract_pandoc_binary(
    data: bytes,
    archive_type: str,
    binary_name: str,
    log_fn=None,
) -> bytes | None:
    """Extract the pandoc executable from archive bytes."""
    import io
    import zipfile

    if archive_type == "zip":
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for member in zf.namelist():
                if member.endswith(binary_name):
                    return zf.read(member)
        return None

    if archive_type == "tar.gz":
        import tarfile
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
            for member in tf.getmembers():
                if member.name.endswith(binary_name) and member.isfile():
                    f = tf.extractfile(member)
                    if f:
                        return f.read()
        return None

    if log_fn:
        log_fn(f"[PANDOC] 不支持的归档类型: {archive_type}")
    return None


def _pandoc_data_dir() -> Path:
    """Return the dependency-managed pandoc binary directory."""

    cwd = Path.cwd()
    venv_candidate = cwd / ".venv"
    if venv_candidate.is_dir():
        base = cwd
    else:

        base = cwd
    target = base / "deps" / "pandoc"
    return target
