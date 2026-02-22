import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


TORCH_CUDA_MATRIX: list[dict] = [
    {"cuda": (11, 8), "tag": "cu118", "torch": "2.7.1", "vision": "0.22.1", "audio": "2.7.1"},
    {"cuda": (12, 1), "tag": "cu121", "torch": "2.5.1", "vision": "0.20.1", "audio": "2.5.1"},
    {"cuda": (12, 4), "tag": "cu124", "torch": "2.5.1", "vision": "0.20.1", "audio": "2.5.1"},
    {"cuda": (12, 6), "tag": "cu126", "torch": "2.7.1", "vision": "0.22.1", "audio": "2.7.1"},
    {"cuda": (12, 8), "tag": "cu128", "torch": "2.7.1", "vision": "0.22.1", "audio": "2.7.1"},
    {"cuda": (12, 9), "tag": "cu129", "torch": "2.8.0", "vision": "0.23.0", "audio": "2.8.0"},
    {"cuda": (13, 0), "tag": "cu130", "torch": "2.9.0", "vision": "0.24.0", "audio": "2.9.0"},
]

TORCH_CPU_PLAN: dict = {"tag": "cpu", "torch": "2.9.0", "vision": "0.24.0", "audio": "2.9.0"}

_SHARED_PTH_NAME = "latexsnipper_shared_torch.pth"


def normalize_mode(mode: str | None) -> str:
    m = (mode or "auto").strip().lower()
    return m if m in ("auto", "cpu", "gpu") else "auto"


def parse_cuda_ver_from_text(text: str) -> tuple[int, int] | None:
    t = (text or "").lower()
    m = re.search(r"release\s*(\d+)\.(\d+)", t)
    if not m:
        m = re.search(r"\bv(\d+)\.(\d+)", t)
    if not m:
        m = re.search(r"cuda version:\s*(\d+)\.(\d+)", t)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def pick_torch_cuda_plan(major: int, minor: int) -> tuple[dict | None, str]:
    if (major, minor) < (11, 8):
        return None, f"检测到 CUDA {major}.{minor}，低于 11.8，当前不适配 GPU 版 PyTorch"

    best = None
    for p in TORCH_CUDA_MATRIX:
        if p["cuda"] <= (major, minor):
            best = p

    if best is None:
        return None, f"检测到 CUDA {major}.{minor}，未匹配到可用 GPU 版本"

    if (major, minor) > TORCH_CUDA_MATRIX[-1]["cuda"]:
        return best, f"检测到 CUDA {major}.{minor}，高于映射上限，回退使用 {best['tag']}"
    return best, f"检测到 CUDA {major}.{minor}，将使用 {best['tag']}"


def detect_torch_gpu_plan(timeout_sec: int = 5) -> tuple[dict | None, str]:
    # Prefer Toolkit version from nvcc.
    try:
        res = subprocess.run(["nvcc", "--version"], capture_output=True, text=True, timeout=timeout_sec)
        out = (res.stdout or "") + "\n" + (res.stderr or "")
        ver = parse_cuda_ver_from_text(out)
        if ver:
            plan, note = pick_torch_cuda_plan(ver[0], ver[1])
            if plan:
                return plan, f"通过 nvcc 检测到 CUDA Toolkit {ver[0]}.{ver[1]}，将使用 {plan['tag']}"
            return None, note
    except Exception:
        pass

    # Fallback to driver capability from nvidia-smi.
    try:
        res = subprocess.run(["nvidia-smi"], capture_output=True, text=True, timeout=timeout_sec)
        out = (res.stdout or "") + "\n" + (res.stderr or "")
        ver = parse_cuda_ver_from_text(out)
        if ver:
            plan, note = pick_torch_cuda_plan(ver[0], ver[1])
            if plan:
                return plan, f"未找到 nvcc，按驱动 CUDA {ver[0]}.{ver[1]} 推断，建议使用 {plan['tag']}"
            return None, note
    except Exception:
        pass

    return None, "未检测到 nvcc / nvidia-smi，无法自动推断 GPU 版本"


def build_torch_pip_command(pyexe: str, mode: str) -> tuple[str, str]:
    m = normalize_mode(mode)
    extra_index = " --extra-index-url https://pypi.org/simple"
    if m == "gpu":
        plan, note = detect_torch_gpu_plan()
        if not plan:
            return "", note
        cmd = (
            f"\"{pyexe}\" -m pip install "
            f"torch=={plan['torch']} torchvision=={plan['vision']} torchaudio=={plan['audio']} "
            f"--index-url https://download.pytorch.org/whl/{plan['tag']}{extra_index}"
        )
        return cmd, note
    cpu = TORCH_CPU_PLAN
    cmd = (
        f"\"{pyexe}\" -m pip install "
        f"torch=={cpu['torch']} torchvision=={cpu['vision']} torchaudio=={cpu['audio']} "
        f"--index-url https://download.pytorch.org/whl/cpu{extra_index}"
    )
    return cmd, "使用 CPU 版本"


def build_torch_pip_args(pyexe: str, mode: str) -> tuple[list[str], str]:
    m = normalize_mode(mode)
    if m == "gpu":
        plan, note = detect_torch_gpu_plan()
        if not plan:
            return [], note
        args = [
            pyexe, "-m", "pip", "install",
            f"torch=={plan['torch']}",
            f"torchvision=={plan['vision']}",
            f"torchaudio=={plan['audio']}",
            "--index-url", f"https://download.pytorch.org/whl/{plan['tag']}",
            "--extra-index-url", "https://pypi.org/simple",
        ]
        return args, note
    cpu = TORCH_CPU_PLAN
    args = [
        pyexe, "-m", "pip", "install",
        f"torch=={cpu['torch']}",
        f"torchvision=={cpu['vision']}",
        f"torchaudio=={cpu['audio']}",
        "--index-url", "https://download.pytorch.org/whl/cpu",
        "--extra-index-url", "https://pypi.org/simple",
    ]
    return args, "使用 CPU 版本"


def python_site_packages(pyexe: str) -> Path | None:
    if not pyexe:
        return None
    p = Path(pyexe)
    candidates = [
        p.parent / "Lib" / "site-packages",
        p.parent.parent / "Lib" / "site-packages",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def _torch_tag_from_dist_info(site: Path) -> str:
    try:
        for d in site.glob("torch-*.dist-info"):
            n = d.name.lower()
            if "+cu" in n:
                tail = n.split("+cu", 1)[1]
                digits = re.match(r"(\d+)", tail)
                if digits:
                    return f"cu{digits.group(1)}"
                return "gpu"
        if (site / "torch").exists():
            return "cpu"
    except Exception:
        pass
    return ""


def detect_torch_info(pyexe: str, timeout_sec: int = 8, run_env: dict | None = None) -> dict:
    info = {
        "present": False,
        "mode": "",
        "cuda_available": False,
        "cuda_version": "",
        "torch_version": "",
        "error": "",
    }
    if not pyexe or not os.path.exists(pyexe):
        info["error"] = "python.exe not found"
        return info

    code = (
        "import json, os, sys\n"
        "def _bootstrap_shared_torch():\n"
        "    _shared_site = (os.environ.get('PIX2TEXT_SHARED_TORCH_SITE', '') or os.environ.get('LATEXSNIPPER_SHARED_TORCH_SITE', '') or '').strip()\n"
        "    if not (_shared_site and os.path.isdir(_shared_site)):\n"
        "        return\n"
        "    _added = False\n"
        "    try:\n"
        "        if _shared_site not in sys.path:\n"
        "            sys.path.insert(0, _shared_site)\n"
        "            _added = True\n"
        "    except Exception:\n"
        "        pass\n"
        "    try:\n"
        "        _torch_lib = os.path.join(_shared_site, 'torch', 'lib')\n"
        "        if os.path.isdir(_torch_lib):\n"
        "            if hasattr(os, 'add_dll_directory'):\n"
        "                os.add_dll_directory(_torch_lib)\n"
        "            os.environ['PATH'] = _torch_lib + os.pathsep + os.environ.get('PATH', '')\n"
        "    except Exception:\n"
        "        pass\n"
        "    try:\n"
        "        try:\n"
        "            import torch  # noqa: F401\n"
        "        except Exception:\n"
        "            pass\n"
        "        try:\n"
        "            import torchvision  # noqa: F401\n"
        "        except Exception:\n"
        "            pass\n"
        "        try:\n"
        "            import torchaudio  # noqa: F401\n"
        "        except Exception:\n"
        "            pass\n"
        "    except Exception:\n"
        "        pass\n"
        "    finally:\n"
        "        if _added:\n"
        "            try:\n"
        "                sys.path.remove(_shared_site)\n"
        "            except Exception:\n"
        "                pass\n"
        "_bootstrap_shared_torch()\n"
        "try:\n"
        " import torch\n"
        " import torchvision\n"
        " cv = getattr(getattr(torch, 'version', None), 'cuda', '') or ''\n"
        " gpu = bool(torch.cuda.is_available())\n"
        " print(json.dumps({'present': True, 'cuda_available': gpu, 'cuda_version': cv, 'torch_version': getattr(torch, '__version__', '')}))\n"
        "except Exception as e:\n"
        " print(json.dumps({'present': False, 'error': str(e)}))\n"
    )
    try:
        res = subprocess.run(
            [pyexe, "-c", code],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            env=run_env,
        )
        out = ((res.stdout or "") + "\n" + (res.stderr or "")).strip()
        payload = None
        for line in reversed(out.splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
                if isinstance(payload, dict):
                    break
            except Exception:
                continue
        if isinstance(payload, dict):
            info.update(payload)
        elif out:
            info["error"] = out[:240]
    except subprocess.TimeoutExpired:
        info["error"] = "timeout"
    except Exception as e:
        info["error"] = str(e)

    if not info.get("present"):
        site = python_site_packages(pyexe)
        if site and (site / "torch").exists() and (site / "torchvision").exists():
            tag = _torch_tag_from_dist_info(site)
            info["present"] = True
            info["cuda_available"] = tag.startswith("cu") or tag == "gpu"
            info["cuda_version"] = tag if tag.startswith("cu") else ""
            info["mode"] = "gpu" if info["cuda_available"] else "cpu"
            info["error"] = ""
        return info

    cuda_ver = str(info.get("cuda_version") or "")
    is_gpu = bool(info.get("cuda_available")) or cuda_ver.startswith("cu") or bool(cuda_ver)
    info["mode"] = "gpu" if is_gpu else "cpu"
    info["error"] = ""
    if is_gpu and cuda_ver and not cuda_ver.startswith("cu"):
        parts = cuda_ver.split(".")
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            info["cuda_version"] = f"cu{parts[0]}{parts[1]}"
    return info


def mode_satisfies(torch_info: dict, mode: str) -> bool:
    if not torch_info or not torch_info.get("present"):
        return False
    m = normalize_mode(mode)
    current = (torch_info.get("mode") or "").lower()
    if m == "auto":
        return True
    return current == m


def inject_shared_torch_env(env: dict, shared_site: str | None) -> dict:
    out = dict(env or {})
    site = (shared_site or "").strip()
    if not site or not os.path.isdir(site):
        out.pop("PIX2TEXT_SHARED_TORCH_SITE", None)
        out.pop("LATEXSNIPPER_SHARED_TORCH_SITE", None)
        return out
    out["PIX2TEXT_SHARED_TORCH_SITE"] = site
    out.pop("LATEXSNIPPER_SHARED_TORCH_SITE", None)
    torch_lib = os.path.join(site, "torch", "lib")
    if os.path.isdir(torch_lib):
        cur = out.get("PATH", "")
        out["PATH"] = f"{torch_lib};{cur}" if cur else torch_lib
    return out


def ensure_shared_torch_link(env_pyexe: str, shared_site: str | None) -> tuple[bool, str]:
    env_site = python_site_packages(env_pyexe)
    if not env_site:
        return False, "env site-packages not found"

    pth_path = env_site / _SHARED_PTH_NAME
    site = (shared_site or "").strip()

    # Always remove legacy full-site .pth path to avoid leaking non-torch deps
    # (e.g. transformers/optimum) into isolated env resolution.
    try:
        if pth_path.exists():
            pth_path.unlink()
    except Exception:
        pass

    if not site or not os.path.isdir(site):
        return True, "shared torch link cleared"

    # 如果共享路径就是当前环境路径，不做 metadata 同步。
    # 否则会先删后拷贝并在“同目录”场景下把 dist-info 误删掉。
    try:
        src_site = Path(site).resolve()
        dst_site = env_site.resolve()
        if src_site == dst_site:
            return True, "shared site is env site, skip metadata sync"
    except Exception:
        src_site = Path(site)

    # Optional metadata copy so pip can consider torch/vision/audio already present.
    try:
        for pattern in ("torch-*.dist-info", "torchvision-*.dist-info", "torchaudio-*.dist-info"):
            existing = list(env_site.glob(pattern))
            for d in existing:
                try:
                    shutil.rmtree(d, ignore_errors=True)
                except Exception:
                    pass
            for src in src_site.glob(pattern):
                dst = env_site / src.name
                try:
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                except Exception:
                    pass
    except Exception:
        pass

    return True, "shared torch metadata synced"


def infer_main_python() -> str:
    pyexe = os.environ.get("LATEXSNIPPER_PYEXE", "") or sys.executable
    return pyexe if os.path.exists(pyexe) else sys.executable
