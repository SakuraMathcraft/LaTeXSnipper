# coding: utf-8

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import sys


_CUDA_DLLS = (
    "cudart64_12.dll",
    "cublas64_12.dll",
    "cublasLt64_12.dll",
    "cufft64_11.dll",
    "curand64_10.dll",
)
_CUDNN_DLLS = ("cudnn64_9.dll",)


@dataclass(frozen=True)
class DllPathStatus:
    name: str
    on_path: tuple[Path, ...]
    candidates: tuple[Path, ...]

    @property
    def missing_from_path(self) -> bool:
        return not self.on_path

    @property
    def candidate_dirs_not_on_path(self) -> tuple[Path, ...]:
        path_dirs = {_norm_dir(item.parent) for item in self.on_path}
        dirs: list[Path] = []
        seen: set[str] = set()
        for item in self.candidates:
            parent = item.parent
            key = _norm_dir(parent)
            if key in path_dirs or key in seen:
                continue
            seen.add(key)
            dirs.append(parent)
        return tuple(dirs)


@dataclass(frozen=True)
class CudaDllDiagnostics:
    dlls: tuple[DllPathStatus, ...]

    def recommended_path_dirs(self) -> tuple[Path, ...]:
        dirs: list[Path] = []
        seen: set[str] = set()
        for dll in self.dlls:
            if not dll.missing_from_path:
                continue
            for path in dll.candidate_dirs_not_on_path:
                key = _norm_dir(path)
                if key in seen:
                    continue
                seen.add(key)
                dirs.append(path)
        return tuple(dirs)

    def format_for_user(self) -> str:
        dirs = self.recommended_path_dirs()
        missing = tuple(dll.name for dll in self.dlls if dll.missing_from_path)
        if dirs:
            return "CUDA/cuDNN DLL 目录未加入 PATH，请查看日志。"
        if missing:
            return "缺少关键 CUDA/cuDNN DLL，请查看日志。"
        return "CUDA/cuDNN PATH 正常，请检查版本或驱动。"

    def format_for_log(self) -> str:
        parts: list[str] = []
        for dll in self.dlls:
            if dll.on_path:
                parts.append(f"{dll.name}=PATH:{dll.on_path[0]}")
                continue
            if dll.candidates:
                dirs = ", ".join(str(path.parent) for path in dll.candidates[:3])
                parts.append(f"{dll.name}=not-in-PATH; candidates: {dirs}")
            else:
                parts.append(f"{dll.name}=missing")
        return "CUDA/cuDNN DLL 检查: " + " | ".join(parts)


def diagnose_cuda_dll_paths() -> CudaDllDiagnostics:
    dlls = tuple(_probe_dll(name) for name in (*_CUDNN_DLLS, *_CUDA_DLLS))
    return CudaDllDiagnostics(dlls=dlls)


def _probe_dll(name: str) -> DllPathStatus:
    on_path = _which_all(name)
    candidates = _find_candidates(name)
    return DllPathStatus(name=name, on_path=on_path, candidates=candidates)


def _which_all(name: str) -> tuple[Path, ...]:
    matches: list[Path] = []
    seen: set[str] = set()
    first = shutil.which(name)
    if first:
        _append_unique(matches, seen, Path(first))
    for raw_dir in os.environ.get("PATH", "").split(os.pathsep):
        if not raw_dir.strip():
            continue
        path = Path(raw_dir.strip().strip('"')) / name
        if path.is_file():
            _append_unique(matches, seen, path)
    return tuple(matches)


def _find_candidates(name: str) -> tuple[Path, ...]:
    matches: list[Path] = []
    seen: set[str] = set()
    for root in _candidate_roots(name):
        _scan_candidate_root(root, name, matches, seen)
    return tuple(matches)


def _candidate_roots(name: str) -> tuple[Path, ...]:
    roots: list[Path] = []
    for env_key in ("CUDA_PATH", "CUDA_HOME"):
        raw = os.environ.get(env_key, "")
        if raw:
            roots.append(Path(raw) / "bin")
            roots.append(Path(raw))
    for env_key, raw in os.environ.items():
        if env_key.startswith("CUDA_PATH_V") and raw:
            roots.append(Path(raw) / "bin")
            roots.append(Path(raw))

    program_files = tuple(
        Path(raw)
        for raw in (
            os.environ.get("ProgramFiles", ""),
            os.environ.get("ProgramW6432", ""),
        )
        if raw
    )
    for base in program_files:
        roots.append(base / "NVIDIA GPU Computing Toolkit" / "CUDA")
        roots.append(base / "NVIDIA" / "CUDNN")
    if name in _CUDNN_DLLS:
        for site in _site_package_roots():
            roots.append(site / "nvidia" / "cudnn" / "bin")
    return _dedupe_existing_roots(roots)


def _scan_candidate_root(root: Path, name: str, matches: list[Path], seen: set[str]) -> None:
    direct = root / name
    if direct.is_file():
        _append_unique(matches, seen, direct)
    if not root.is_dir():
        return
    try:
        for path in root.rglob(name):
            if len(matches) >= 12:
                return
            if path.is_file():
                _append_unique(matches, seen, path)
    except Exception:
        return


def _site_package_roots() -> tuple[Path, ...]:
    roots: list[Path] = []
    for base in (Path(sys.prefix), Path(sys.base_prefix)):
        roots.append(base / "Lib" / "site-packages")
    return _dedupe_existing_roots(roots)


def _dedupe_existing_roots(paths: list[Path]) -> tuple[Path, ...]:
    roots: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        try:
            resolved = path.resolve()
        except Exception:
            resolved = path
        key = _norm_dir(resolved)
        if key in seen or not resolved.exists():
            continue
        seen.add(key)
        roots.append(resolved)
    return tuple(roots)


def _append_unique(items: list[Path], seen: set[str], path: Path) -> None:
    try:
        resolved = path.resolve()
    except Exception:
        resolved = path
    key = str(resolved).casefold()
    if key in seen:
        return
    seen.add(key)
    items.append(resolved)


def _norm_dir(path: Path) -> str:
    try:
        return str(path.resolve()).casefold()
    except Exception:
        return str(path).casefold()


__all__ = ["CudaDllDiagnostics", "DllPathStatus", "diagnose_cuda_dll_paths"]
