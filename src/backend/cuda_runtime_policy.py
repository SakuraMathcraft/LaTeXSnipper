# coding: utf-8

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import subprocess
import sys


CUDA11_ORT_INDEX_URL = (
    "https://aiinfra.pkgs.visualstudio.com/PublicPackages/"
    "_packaging/onnxruntime-cuda-11/pypi/simple/"
)
CUDA13_ORT_NIGHTLY_INDEX_URL = (
    "https://aiinfra.pkgs.visualstudio.com/PublicPackages/"
    "_packaging/ort-cuda-13-nightly/pypi/simple/"
)


@dataclass(frozen=True)
class CudaRuntimeInfo:
    major: int | None = None
    minor: int | None = None
    source: str = "unknown"
    raw: str = ""

    @property
    def version_text(self) -> str:
        if self.major is None:
            return "unknown"
        if self.minor is None:
            return str(self.major)
        return f"{self.major}.{self.minor}"


@dataclass(frozen=True)
class OnnxRuntimeGpuPolicy:
    requirement: str
    cuda: CudaRuntimeInfo
    expected_cuda_major: int | None
    expected_cudnn_major: int | None
    index_url: str = ""
    pre: bool = False
    source_label: str = "PyPI"
    warning: str = ""

    def pip_install_args(self) -> tuple[str, ...]:
        args: list[str] = [self.requirement]
        if self.pre:
            args.append("--pre")
        if self.index_url:
            args.extend(["--index-url", self.index_url])
        return tuple(args)

    def pip_command(self) -> str:
        return "pip install " + " ".join(_quote_cmd_arg(arg) for arg in self.pip_install_args())


@dataclass(frozen=True)
class DllRequirement:
    family: str
    display_name: str
    patterns: tuple[str, ...]
    expected_names: tuple[str, ...] = ()


def detect_cuda_runtime(*, use_nvcc: bool = True) -> CudaRuntimeInfo:
    override = _parse_cuda_version(os.environ.get("MATHCRAFT_CUDA_VERSION", ""), "MATHCRAFT_CUDA_VERSION")
    if override.major is not None:
        return override

    for key in ("CUDA_PATH", "CUDA_HOME"):
        info = _parse_cuda_version(os.environ.get(key, ""), key)
        if info.major is not None:
            return info

    env_versions: list[CudaRuntimeInfo] = []
    for key, raw in os.environ.items():
        if not key.upper().startswith("CUDA_PATH_V"):
            continue
        info = _parse_cuda_version(key, key)
        if info.major is None:
            info = _parse_cuda_version(raw, key)
        if info.major is not None:
            env_versions.append(info)
    if env_versions:
        return _highest_cuda_version(env_versions)

    for raw_dir in os.environ.get("PATH", "").split(os.pathsep):
        info = _parse_cuda_version(raw_dir, "PATH")
        if info.major is not None:
            return info

    info = _detect_cuda_from_path_dlls()
    if info.major is not None:
        return info

    if use_nvcc:
        info = _detect_nvcc_cuda_version()
        if info.major is not None:
            return info

    return CudaRuntimeInfo()


def onnxruntime_cpu_spec(pyexe: str | Path | None = None, python_version: tuple[int, int] | None = None) -> str:
    pyver = python_version or python_version_for_executable(pyexe)
    if pyver >= (3, 13):
        return "onnxruntime>=1.20,<1.26"
    return "onnxruntime>=1.19.2,<1.26"


def onnxruntime_gpu_spec(pyexe: str | Path | None = None, python_version: tuple[int, int] | None = None) -> str:
    return onnxruntime_gpu_policy(pyexe=pyexe, python_version=python_version).requirement


def onnxruntime_gpu_policy(
    pyexe: str | Path | None = None,
    *,
    cuda_info: CudaRuntimeInfo | None = None,
    python_version: tuple[int, int] | None = None,
) -> OnnxRuntimeGpuPolicy:
    cuda = cuda_info or detect_cuda_runtime()
    pyver = python_version or python_version_for_executable(pyexe)

    if cuda.major == 11:
        requirement = "onnxruntime-gpu>=1.20,<1.21" if pyver >= (3, 13) else "onnxruntime-gpu>=1.19.2,<1.21"
        return OnnxRuntimeGpuPolicy(
            requirement=requirement,
            cuda=cuda,
            expected_cuda_major=11,
            expected_cudnn_major=8,
            index_url=CUDA11_ORT_INDEX_URL,
            source_label="ORT CUDA 11 feed",
        )

    if cuda.major is not None and cuda.major >= 13:
        return OnnxRuntimeGpuPolicy(
            requirement="onnxruntime-gpu",
            cuda=cuda,
            expected_cuda_major=cuda.major,
            expected_cudnn_major=9,
            index_url=CUDA13_ORT_NIGHTLY_INDEX_URL,
            pre=True,
            source_label="ORT CUDA 13 nightly feed",
            warning=(
                "CUDA 13 uses ONNX Runtime nightly GPU wheels; stable PyPI "
                "onnxruntime-gpu wheels currently target CUDA 12.x."
            ),
        )

    requirement = "onnxruntime-gpu>=1.20,<1.26" if pyver >= (3, 13) else "onnxruntime-gpu>=1.19.2,<1.26"
    warning = ""
    if cuda.major is not None and cuda.major < 11:
        warning = (
            f"CUDA {cuda.version_text} is outside the supported modern ONNX Runtime GPU range; "
            "falling back to CUDA 12 PyPI wheels."
        )
    return OnnxRuntimeGpuPolicy(
        requirement=requirement,
        cuda=cuda,
        expected_cuda_major=12 if cuda.major is not None else None,
        expected_cudnn_major=9 if cuda.major is not None else None,
        source_label="PyPI CUDA 12 wheels",
        warning=warning,
    )


def cuda_dll_requirements(cuda_info: CudaRuntimeInfo | None = None) -> tuple[DllRequirement, ...]:
    info = cuda_info or detect_cuda_runtime()
    major = info.major

    if major == 11:
        return (
            _exact_req("cudnn", "cudnn64_8.dll"),
            _exact_req("cuda-runtime", "cudart64_110.dll"),
            _exact_req("cublas", "cublas64_11.dll"),
            _exact_req("cublaslt", "cublasLt64_11.dll"),
            _exact_req("cufft", "cufft64_10.dll"),
            _exact_req("curand", "curand64_10.dll"),
        )

    if major == 12:
        return (
            _exact_req("cudnn", "cudnn64_9.dll"),
            _exact_req("cuda-runtime", "cudart64_12.dll"),
            _exact_req("cublas", "cublas64_12.dll"),
            _exact_req("cublaslt", "cublasLt64_12.dll"),
            _exact_req("cufft", "cufft64_11.dll"),
            _exact_req("curand", "curand64_10.dll"),
        )

    if major is not None and major >= 13:
        return (
            _exact_req("cudnn", "cudnn64_9.dll"),
            _exact_req("cuda-runtime", f"cudart64_{major}.dll"),
            _exact_req("cublas", f"cublas64_{major}.dll"),
            _exact_req("cublaslt", f"cublasLt64_{major}.dll"),
            _wildcard_req("cufft", "cufft64_*.dll"),
            _wildcard_req("curand", "curand64_*.dll"),
        )

    return (
        _wildcard_req("cudnn", "cudnn64_*.dll"),
        _wildcard_req("cuda-runtime", "cudart64_*.dll"),
        _wildcard_req("cublas", "cublas64_*.dll"),
        _wildcard_req("cublaslt", "cublasLt64_*.dll"),
        _wildcard_req("cufft", "cufft64_*.dll"),
        _wildcard_req("curand", "curand64_*.dll"),
    )


def python_version_for_executable(pyexe: str | Path | None = None) -> tuple[int, int]:
    if not pyexe:
        return sys.version_info[:2]
    try:
        path = Path(pyexe)
        if path.resolve() == Path(sys.executable).resolve():
            return sys.version_info[:2]
        if not path.exists():
            return sys.version_info[:2]
        result = subprocess.run(
            [str(path), "-c", "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=_subprocess_creationflags(),
        )
        text = (result.stdout or "").strip().splitlines()[-1:]
        if text:
            major, minor = text[0].split(".", 1)
            return int(major), int(minor)
    except Exception:
        pass
    return sys.version_info[:2]


def _parse_cuda_version(text: str | None, source: str) -> CudaRuntimeInfo:
    raw = str(text or "").strip()
    if not raw:
        return CudaRuntimeInfo(source=source, raw=raw)

    env_match = re.search(r"CUDA_PATH_V(?P<major>\d+)(?:_(?P<minor>\d+))?", raw, re.IGNORECASE)
    if env_match:
        return _version_from_match(env_match, source, raw)

    patterns = (
        r"^(?P<major>\d{1,2})(?:\.(?P<minor>\d+))?$",
        r"(?:CUDA\s+Version|release)\s*(?P<major>\d{1,2})(?:\.(?P<minor>\d+))?",
        r"(?:^|[\\/])v(?P<major>\d{1,2})(?:[._](?P<minor>\d+))?(?:[\\/]|$)",
        r"(?:^|[\\/])cuda[-_ ]?(?P<major>\d{1,2})(?:[._](?P<minor>\d+))?(?:[\\/]|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, raw, re.IGNORECASE)
        if match:
            return _version_from_match(match, source, raw)
    return CudaRuntimeInfo(source=source, raw=raw)


def _version_from_match(match: re.Match[str], source: str, raw: str) -> CudaRuntimeInfo:
    try:
        major = int(match.group("major"))
        minor_raw = match.groupdict().get("minor")
        minor = int(minor_raw) if minor_raw is not None else None
    except Exception:
        return CudaRuntimeInfo(source=source, raw=raw)
    if major < 1 or major > 30:
        return CudaRuntimeInfo(source=source, raw=raw)
    return CudaRuntimeInfo(major=major, minor=minor, source=source, raw=raw)


def _detect_nvcc_cuda_version() -> CudaRuntimeInfo:
    try:
        result = subprocess.run(
            ["nvcc", "--version"],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=3,
            creationflags=_subprocess_creationflags(),
        )
    except Exception:
        return CudaRuntimeInfo(source="nvcc")
    output = f"{result.stdout or ''}\n{result.stderr or ''}"
    info = _parse_cuda_version(output, "nvcc")
    if info.major is not None:
        return info
    return CudaRuntimeInfo(source="nvcc", raw=output)


def _detect_cuda_from_path_dlls() -> CudaRuntimeInfo:
    for raw_dir in os.environ.get("PATH", "").split(os.pathsep):
        if not raw_dir.strip():
            continue
        directory = Path(raw_dir.strip().strip('"'))
        if not directory.is_dir():
            continue
        try:
            matches = sorted(directory.glob("cudart64_*.dll"))
        except Exception:
            continue
        for path in matches:
            match = re.match(r"cudart64_(?P<suffix>\d+)\.dll$", path.name, re.IGNORECASE)
            if not match:
                continue
            info = _cuda_version_from_cudart_suffix(match.group("suffix"), str(path))
            if info.major is not None:
                return info
    return CudaRuntimeInfo(source="PATH:cudart")


def _cuda_version_from_cudart_suffix(suffix: str, raw: str) -> CudaRuntimeInfo:
    if suffix == "110":
        return CudaRuntimeInfo(major=11, minor=None, source="PATH:cudart", raw=raw)
    try:
        major = int(suffix)
    except Exception:
        return CudaRuntimeInfo(source="PATH:cudart", raw=raw)
    if major < 1 or major > 30:
        return CudaRuntimeInfo(source="PATH:cudart", raw=raw)
    return CudaRuntimeInfo(major=major, minor=None, source="PATH:cudart", raw=raw)


def _highest_cuda_version(items: list[CudaRuntimeInfo]) -> CudaRuntimeInfo:
    return max(items, key=lambda item: (item.major or 0, item.minor if item.minor is not None else -1))


def _exact_req(family: str, name: str) -> DllRequirement:
    return DllRequirement(family=family, display_name=name, patterns=(name,), expected_names=(name,))


def _wildcard_req(family: str, pattern: str) -> DllRequirement:
    return DllRequirement(family=family, display_name=pattern, patterns=(pattern,))


def _subprocess_creationflags() -> int:
    if os.name != "nt":
        return 0
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _quote_cmd_arg(arg: str) -> str:
    if not arg:
        return '""'
    if any(ch.isspace() or ch in '<>|&"' for ch in arg):
        return '"' + arg.replace('"', '\\"') + '"'
    return arg


__all__ = [
    "CUDA11_ORT_INDEX_URL",
    "CUDA13_ORT_NIGHTLY_INDEX_URL",
    "CudaRuntimeInfo",
    "DllRequirement",
    "OnnxRuntimeGpuPolicy",
    "cuda_dll_requirements",
    "detect_cuda_runtime",
    "onnxruntime_cpu_spec",
    "onnxruntime_gpu_policy",
    "onnxruntime_gpu_spec",
    "python_version_for_executable",
]
