import re
import subprocess
import sys
from pathlib import Path

from bootstrap.deps_context import flags
from bootstrap.deps_state import (
    normalize_chosen_layers as _normalize_chosen_layers_impl,
    sanitize_state_layers as _sanitize_state_layers_impl,
)


ORT_CPU_SPEC = "onnxruntime"


ORT_GPU_DEFAULT_SPEC = "onnxruntime-gpu"


LAYER_MAP = {
    "BASIC": [
        "lxml~=4.9.3",
        "pillow~=11.0.0", "pyperclip~=1.11.0",
        "requests~=2.32.5",
        "certifi>=2024.8.30",
        "psutil~=7.1.0",
    ],
    "CORE": [
        "transformers==4.55.4",
        "tokenizers==0.21.4",
        "opencv-python==4.13.0.92",
        "rapidocr==3.5.0",
        "numpy>=1.26,<3",
        "flatbuffers>=24.3.25",
        "protobuf>=3.20,<5",
        "pymupdf~=1.27.2.2",
    ],
    "MATHCRAFT_CPU": [
        ORT_CPU_SPEC,
    ],
    "MATHCRAFT_GPU": [
        ORT_GPU_DEFAULT_SPEC,
    ],
    "PANDOC": [
        "pypandoc>=1.15",
    ],
}


MATHCRAFT_RUNTIME_LAYERS = ("MATHCRAFT_CPU", "MATHCRAFT_GPU")


LAYER_DISPLAY_NAMES = {
    "BASIC": "基础依赖",
    "CORE": "核心功能",
    "MATHCRAFT_CPU": "CPU 推理后端",
    "MATHCRAFT_GPU": "GPU 推理后端",
    "PANDOC": "Pandoc 文档导出",
}


def layer_display_name(layer: str) -> str:
    return LAYER_DISPLAY_NAMES.get(str(layer), str(layer))


def _sanitize_state_layers(state_path: Path, state: dict | None = None) -> dict:
    return _sanitize_state_layers_impl(
        state_path,
        valid_layers=set(LAYER_MAP),
        runtime_layers=MATHCRAFT_RUNTIME_LAYERS,
        state=state,
    )


def _normalize_chosen_layers(layers: list[str] | None) -> list[str]:
    return _normalize_chosen_layers_impl(layers, valid_layers=set(LAYER_MAP))


def _split_spec_name(spec: str) -> tuple[str, str]:
    """Return (package_name_lower, constraint_part)."""
    m = re.match(r"\s*([A-Za-z0-9_.\-]+)\s*(.*)$", spec or "")
    if not m:
        return "", ""
    return m.group(1).lower(), (m.group(2) or "").strip()


def _version_satisfies_spec(pkg_name: str, installed_ver: str, spec: str) -> bool:
    """Check whether installed version satisfies requirement spec."""
    name, constraint = _split_spec_name(spec)
    if not name:
        return True
    if not constraint:
        return True
    if pkg_name and name != pkg_name.lower():
        return True
    try:
        from packaging.specifiers import SpecifierSet
        from packaging.version import Version
        return Version(installed_ver or "") in SpecifierSet(constraint)
    except Exception:
        return True


def _filter_packages(pkgs):
    res = []
    seen = set()
    for spec in pkgs:
        name = re.split(r'[<>=!~ ]', spec, 1)[0].strip().lower()
        if name in seen:
            continue
        seen.add(name)
        res.append(spec)
    return _reorder_mathcraft_install_specs(res)


def _reorder_mathcraft_install_specs(pkgs, gpu_runtime_first=False):
    """Keep MathCraft / ONNX dependency chain in a stable order to reduce pip backtracking."""
    if not pkgs:
        return []
    names = {
        re.split(r'[<>=!~ ]', spec, 1)[0].strip().lower()
        for spec in pkgs
    }
    if gpu_runtime_first or "onnxruntime-gpu" in names:
        priority = (
            "onnxruntime-gpu",
            "transformers",
            "tokenizers",
            "rapidocr",
            "opencv-python",
            "pymupdf",
        )
    else:
        priority = (
            "onnxruntime",
            "transformers",
            "tokenizers",
            "rapidocr",
            "opencv-python",
            "pymupdf",
        )
    grouped = {k: [] for k in priority}
    tail = []
    for spec in pkgs:
        name = re.split(r'[<>=!~ ]', spec, 1)[0].strip().lower()
        if name in grouped:
            grouped[name].append(spec)
        else:
            tail.append(spec)
    out = []
    for k in priority:
        out.extend(grouped[k])
    out.extend(tail)
    return out


def _gpu_available():
    if sys.platform == "darwin":
        return False
    try:
        r = subprocess.run(["nvidia-smi"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", timeout=2, creationflags=flags)
        return r.returncode == 0
    except Exception:
        return False


def _cuda_toolkit_available():
    if sys.platform == "darwin":
        return False
    try:
        r = subprocess.run(
            ["nvcc", "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=2,
            creationflags=flags,
        )
    except Exception:
        return False
    output = f"{r.stdout or ''}\n{r.stderr or ''}".lower()
    return r.returncode == 0 and "cuda" in output


def _diagnose_install_failure(output: str, returncode: int) -> str:
    """Diagnose common package installation failures."""
    output_lower = output.lower()

    if ("antlr4-python3-runtime" in output_lower) and ("bdist_wheel" in output_lower):
        return "antlr4-python3-runtime 构建环境缺少 wheel，可先修复 pip/setuptools/wheel"


    if any(x in output_lower for x in [
        "permission denied",
        "access is denied",
        "being used by another process",
        "permissionerror",
        "winerror 5",
        "winerror 32",
        "errno 13",
    ]):
        return "依赖文件被占用或依赖目录不可写"


    if any(x in output_lower for x in [
        "conflicting dependencies",
        "incompatible",
        "no matching distribution",
        "could not find a version",
        "resolutionimpossible",
        "package requires",
    ]):
        return "依赖版本冲突"


    if any(x in output_lower for x in [
        "connection refused",
        "connection timed out",
        "could not fetch url",
        "network is unreachable",
        "name or service not known",
        "getaddrinfo failed",
        "ssl: certificate",
        "readtimeouterror",
        "connectionerror",
    ]):
        return "网络连接失败，请检查网络或更换下载源"


    if any(x in output_lower for x in [
        "no space left",
        "disk full",
        "not enough space",
        "oserror: [errno 28]",
    ]):
        return "磁盘空间不足"


    if any(x in output_lower for x in [
        "building wheel",
        "failed building",
        "error: command",
        "microsoft visual c++",
        "vcvarsall.bat",
        "cl.exe",
    ]):
        return "本地编译失败，可能缺少所需的编译工具链"


    if any(x in output_lower for x in [
        "requires python",
        "python_requires",
        "not supported",
    ]):
        return "当前 Python 版本不受该依赖支持"


    if any(x in output_lower for x in [
        "pip._internal",
        "attributeerror",
        "modulenotfounderror: no module named 'pip'",
    ]):
        return "pip 不可用或版本过低"


    if any(x in output_lower for x in [
        "cuda",
        "cudnn",
        "nvidia",
        "gpu",
    ]) and "error" in output_lower:
        return "CUDA/GPU 运行时不兼容"


    if returncode == 1:
        return f"pip 返回错误码 {returncode}，请查看上方日志"
    elif returncode == 2:
        return f"pip 命令参数错误（错误码 {returncode}）"
    else:
        return f"pip 返回错误码 {returncode}，请查看上方日志"
