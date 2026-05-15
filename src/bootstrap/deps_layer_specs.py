import re
import subprocess
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
        "certifi~=2026.2.25",
        "psutil~=7.1.0",
    ],
    "CORE": [
        "transformers==4.55.4",
        "tokenizers==0.21.4",
        "sentencepiece==0.2.0",
        "opencv-python==4.13.0.92",
        "rapidocr==3.5.0",
        "numpy>=1.26,<3",
        "flatbuffers>=24.3.25",
        "coloredlogs>=15.0.1",
        "sympy>=1.13,<1.15",
        "protobuf>=3.20,<5",
        "latex2mathml>=3.81.0",
        "matplotlib~=3.10.8",
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
    try:
        r = subprocess.run(["nvidia-smi"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", timeout=2, creationflags=flags)
        return r.returncode == 0
    except Exception:
        return False


def _cuda_toolkit_available():
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
        return "🧩 antlr4-python3-runtime 构建环境缺少 wheel - 可先补齐 pip/setuptools/wheel 并关闭 build isolation"


    if any(x in output_lower for x in [
        "permission denied",
        "access is denied",
        "being used by another process",
        "permissionerror",
        "winerror 5",
        "winerror 32",
        "errno 13",
    ]):
        return "🔒 文件被占用或权限不足 - 请关闭程序后重试，或以管理员身份运行"


    if any(x in output_lower for x in [
        "conflicting dependencies",
        "incompatible",
        "no matching distribution",
        "could not find a version",
        "resolutionimpossible",
        "package requires",
    ]):
        return "⚠️ 依赖版本冲突 - 某些包的版本要求互相矛盾"


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
        return "🌐 网络连接失败 - 请检查网络或尝试使用镜像源"


    if any(x in output_lower for x in [
        "no space left",
        "disk full",
        "not enough space",
        "oserror: [errno 28]",
    ]):
        return "💾 磁盘空间不足 - 请清理磁盘后重试"


    if any(x in output_lower for x in [
        "building wheel",
        "failed building",
        "error: command",
        "microsoft visual c++",
        "vcvarsall.bat",
        "cl.exe",
    ]):
        return "🔧 编译失败 - 可能缺少 Visual C++ Build Tools"


    if any(x in output_lower for x in [
        "requires python",
        "python_requires",
        "not supported",
    ]):
        return "🐍 Python 版本不兼容 - 该包不支持当前 Python 版本"


    if any(x in output_lower for x in [
        "pip._internal",
        "attributeerror",
        "modulenotfounderror: no module named 'pip'",
    ]):
        return "📦 pip 损坏或版本过低 - 请先升级 pip"


    if any(x in output_lower for x in [
        "cuda",
        "cudnn",
        "nvidia",
        "gpu",
    ]) and "error" in output_lower:
        return "🎮 CUDA/GPU 相关错误 - 请检查 CUDA 版本是否匹配"


    if returncode == 1:
        return f"❓ 一般错误 (code={returncode}) - 请查看上方日志获取详情"
    elif returncode == 2:
        return f"❓ 命令行语法错误 (code={returncode})"
    else:
        return f"❓ 未知错误 (code={returncode}) - 请查看上方日志获取详情"
