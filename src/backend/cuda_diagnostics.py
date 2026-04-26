# coding: utf-8

from __future__ import annotations

from dataclasses import dataclass, field
import fnmatch
import os
from pathlib import Path
import sys

from .cuda_runtime_policy import (
    CudaRuntimeInfo,
    DllRequirement,
    cuda_dll_requirements,
    detect_cuda_runtime,
)


@dataclass(frozen=True)
class DllPathStatus:
    name: str
    on_path: tuple[Path, ...]
    candidates: tuple[Path, ...]
    family: str = ""

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
    cuda: CudaRuntimeInfo = field(default_factory=CudaRuntimeInfo)

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
        cuda_text = self.cuda.version_text
        if dirs:
            return f"CUDA/cuDNN DLL 目录未加入 PATH（检测到 CUDA {cuda_text}），请查看日志。"
        if missing:
            return f"缺少关键 CUDA/cuDNN DLL（检测到 CUDA {cuda_text}），请查看日志。"
        return f"CUDA/cuDNN PATH 正常（检测到 CUDA {cuda_text}），请检查版本或驱动。"

    def format_for_log(self) -> str:
        parts: list[str] = [f"detected-cuda={self.cuda.version_text}({self.cuda.source})"]
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


def diagnose_cuda_dll_paths(cuda_info: CudaRuntimeInfo | None = None) -> CudaDllDiagnostics:
    info = cuda_info or detect_cuda_runtime()
    dlls = tuple(_probe_dll(req) for req in cuda_dll_requirements(info))
    return CudaDllDiagnostics(dlls=dlls, cuda=info)


def _probe_dll(req: DllRequirement) -> DllPathStatus:
    on_path = _which_all(req)
    candidates = _find_candidates(req)
    return DllPathStatus(name=req.display_name, on_path=on_path, candidates=candidates, family=req.family)


def _which_all(req: DllRequirement) -> tuple[Path, ...]:
    matches: list[Path] = []
    seen: set[str] = set()
    for raw_dir in os.environ.get("PATH", "").split(os.pathsep):
        if not raw_dir.strip():
            continue
        directory = Path(raw_dir.strip().strip('"'))
        for path in _direct_matches(directory, req):
            _append_unique(matches, seen, path)
    return tuple(matches)


def _find_candidates(req: DllRequirement) -> tuple[Path, ...]:
    matches: list[Path] = []
    seen: set[str] = set()
    for root in _candidate_roots(req):
        _scan_candidate_root(root, req, matches, seen)
    return tuple(matches)


def _candidate_roots(req: DllRequirement) -> tuple[Path, ...]:
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

    for site in _site_package_roots():
        roots.append(site / "torch" / "lib")
        roots.extend(_nvidia_site_package_roots(site, req.family))
    return _dedupe_existing_roots(roots)


def _nvidia_site_package_roots(site: Path, family: str) -> tuple[Path, ...]:
    package_dirs = {
        "cuda-runtime": ("cuda_runtime",),
        "cublas": ("cublas",),
        "cublaslt": ("cublas",),
        "cufft": ("cufft",),
        "curand": ("curand",),
        "cudnn": ("cudnn",),
    }.get(family, ())
    return tuple(site / "nvidia" / package / "bin" for package in package_dirs)


def _scan_candidate_root(root: Path, req: DllRequirement, matches: list[Path], seen: set[str]) -> None:
    for path in _direct_matches(root, req):
        _append_unique(matches, seen, path)
    if not root.is_dir():
        return
    try:
        for pattern in req.patterns:
            for path in root.rglob(pattern):
                if len(matches) >= 12:
                    return
                if path.is_file() and _matches_requirement(path.name, req):
                    _append_unique(matches, seen, path)
    except Exception:
        return


def _direct_matches(directory: Path, req: DllRequirement) -> tuple[Path, ...]:
    if not directory.is_dir():
        return ()
    matches: list[Path] = []
    expected = req.expected_names
    if expected:
        for name in expected:
            path = directory / name
            if path.is_file():
                matches.append(path)
        return tuple(matches)
    try:
        for pattern in req.patterns:
            for path in directory.glob(pattern):
                if path.is_file() and _matches_requirement(path.name, req):
                    matches.append(path)
    except Exception:
        return ()
    return tuple(matches)


def _matches_requirement(filename: str, req: DllRequirement) -> bool:
    name = filename.casefold()
    if req.expected_names:
        return name in {item.casefold() for item in req.expected_names}
    return any(fnmatch.fnmatchcase(name, pattern.casefold()) for pattern in req.patterns)


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
