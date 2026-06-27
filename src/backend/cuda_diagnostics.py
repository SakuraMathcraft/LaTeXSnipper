# coding: utf-8

from __future__ import annotations

from dataclasses import dataclass, field
import fnmatch
import os
from pathlib import Path
import subprocess
import sys
import sysconfig

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


@dataclass(frozen=True)
class SharedLibraryStatus:
    name: str
    found: tuple[Path, ...]

    @property
    def missing(self) -> bool:
        return not self.found


@dataclass(frozen=True)
class CudaSharedLibraryDiagnostics:
    libraries: tuple[SharedLibraryStatus, ...]

    def format_for_user(self) -> str:
        missing = [item.name for item in self.libraries if item.missing]
        if missing:
            names = ", ".join(missing[:4])
            suffix = " 等" if len(missing) > 4 else ""
            return f"缺少关键 CUDA/cuDNN 共享库（{names}{suffix}），请检查 NVIDIA 驱动、CUDA/cuDNN 安装和 LD_LIBRARY_PATH。"
        return "CUDA/cuDNN 共享库路径正常，请检查版本、驱动或 onnxruntime-gpu 兼容性。"

    def format_for_log(self) -> str:
        parts: list[str] = []
        for item in self.libraries:
            if item.found:
                paths = ", ".join(str(path) for path in item.found[:3])
                parts.append(f"{item.name}=found:{paths}")
            else:
                parts.append(f"{item.name}=missing")
        return "CUDA/cuDNN SO 检查: " + " | ".join(parts)


def diagnose_cuda_shared_libraries() -> CudaSharedLibraryDiagnostics:
    names = (
        "libcudart.so",
        "libcublas.so",
        "libcublasLt.so",
        "libcufft.so",
        "libcurand.so",
        "libcudnn.so",
    )
    return CudaSharedLibraryDiagnostics(
        libraries=tuple(SharedLibraryStatus(name=name, found=_find_shared_library(name)) for name in names)
    )


def _probe_dll(req: DllRequirement) -> DllPathStatus:
    on_path = _which_all(req)
    candidates = _find_candidates(req)
    return DllPathStatus(name=req.display_name, on_path=on_path, candidates=candidates, family=req.family)


def _find_shared_library(name: str) -> tuple[Path, ...]:
    matches: list[Path] = []
    seen: set[str] = set()
    for directory in _linux_library_search_dirs():
        for path in _direct_shared_library_matches(directory, name):
            _append_unique(matches, seen, path)
    for path in _ldconfig_matches(name):
        _append_unique(matches, seen, path)
    return tuple(matches)


def _linux_library_search_dirs() -> tuple[Path, ...]:
    roots: list[Path] = []
    for raw in os.environ.get("LD_LIBRARY_PATH", "").split(os.pathsep):
        if raw.strip():
            roots.append(Path(raw.strip()))
    for env_key in ("CUDA_HOME", "CUDA_PATH"):
        raw = os.environ.get(env_key, "")
        if raw:
            root = Path(raw)
            roots.extend((root / "lib64", root / "lib", root))
    roots.extend(
        Path(path)
        for path in (
            "/usr/local/cuda/lib64",
            "/usr/local/cuda/lib",
            "/usr/lib/x86_64-linux-gnu",
            "/usr/lib64",
            "/usr/lib",
            "/lib/x86_64-linux-gnu",
            "/lib64",
        )
    )
    for site in _site_package_roots():
        roots.append(site / "torch" / "lib")
        roots.append(site / "nvidia")
    return _dedupe_existing_roots(roots)


def _direct_shared_library_matches(directory: Path, name: str) -> tuple[Path, ...]:
    if not directory.is_dir():
        return ()
    matches: list[Path] = []
    patterns = (name, f"{name}.*")
    try:
        for pattern in patterns:
            for path in directory.rglob(pattern):
                if path.is_file() or path.is_symlink():
                    matches.append(path)
                    if len(matches) >= 12:
                        return tuple(matches)
    except Exception:
        return tuple(matches)
    return tuple(matches)


def _ldconfig_matches(name: str) -> tuple[Path, ...]:
    if sys.platform != "linux":
        return ()
    try:
        proc = subprocess.run(
            ["ldconfig", "-p"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=2.0,
        )
    except Exception:
        return ()
    if proc.returncode != 0:
        return ()
    matches: list[Path] = []
    for raw_line in proc.stdout.splitlines():
        line = raw_line.strip()
        if not line.startswith(name):
            continue
        marker = "=>"
        if marker not in line:
            continue
        path = Path(line.rsplit(marker, 1)[-1].strip())
        if path.exists():
            matches.append(path)
    return tuple(matches)


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
    for key in ("purelib", "platlib"):
        raw = sysconfig.get_path(key)
        if raw:
            roots.append(Path(raw))
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


__all__ = [
    "CudaDllDiagnostics",
    "CudaSharedLibraryDiagnostics",
    "DllPathStatus",
    "SharedLibraryStatus",
    "diagnose_cuda_dll_paths",
    "diagnose_cuda_shared_libraries",
]
