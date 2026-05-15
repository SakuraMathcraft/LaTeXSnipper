import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from backend.cuda_runtime_policy import onnxruntime_gpu_policy
from bootstrap.deps_context import (
    PIP_INSTALL_SUPPRESS_ARGS,
    flags,
    pip_ready_event,
    safe_run,
    subprocess_lock,
)
from bootstrap.deps_pip_runner import PipInstallRunner
from bootstrap.deps_python_runtime import site_packages_root as _site_packages_root
from bootstrap.deps_layer_specs import _diagnose_install_failure, _version_satisfies_spec


CRITICAL_VERSIONS = {
    "numpy": "numpy>=1.26,<3",
    "sympy": "sympy>=1.13,<1.15",
    "flatbuffers": "flatbuffers>=24.3.25",
    "packaging": "packaging>=23",
    "coloredlogs": "coloredlogs>=15.0.1",
    "rapidocr": "rapidocr==3.5.0",
    "protobuf": "protobuf>=3.20,<5",
}


RUNTIME_IMPORT_CHECKS = {
    "numpy": "numpy",
    "sympy": "sympy",
    "flatbuffers": "flatbuffers",
    "packaging": "packaging",
    "coloredlogs": "coloredlogs",
    "protobuf": "google.protobuf",
}


def _cleanup_pip_interrupted_leftovers(pyexe: str | Path, log_fn=None) -> int:
    """Remove pip's half-uninstalled '~pkg' leftovers from the target site-packages."""
    try:
        site_packages = _site_packages_root(Path(pyexe))
    except Exception:
        site_packages = None
    if not site_packages or not site_packages.exists():
        return 0

    removed: list[str] = []
    for item in site_packages.iterdir():
        if not item.name.startswith("~"):
            continue
        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
            removed.append(item.name)
        except Exception as e:
            if log_fn:
                log_fn(f"  [WARN] 清理 pip 残留失败 {item.name}: {e}")

    if removed and log_fn:
        shown = ", ".join(removed[:8])
        suffix = "..." if len(removed) > 8 else ""
        log_fn(f"[INFO] 已清理 pip 中断残留: {shown}{suffix}")
    return len(removed)


def _cleanup_orphan_onnxruntime_namespace(
    pyexe: str | Path,
    installed_map: dict | None = None,
    log_fn=None,
) -> int:
    """
    Remove an onnxruntime package directory left behind without pip metadata.

    pip cannot uninstall this state because no onnxruntime*.dist-info exists,
    but Python still imports the namespace and then misses get_available_providers.
    """
    current = installed_map if installed_map is not None else _current_installed(pyexe)
    if "onnxruntime" in current or "onnxruntime-gpu" in current:
        return 0
    try:
        site_packages = _site_packages_root(Path(pyexe))
    except Exception:
        site_packages = None
    if not site_packages or not site_packages.exists():
        return 0

    target = site_packages / "onnxruntime"
    if not target.exists():
        return 0
    try:
        if not target.resolve().is_relative_to(site_packages.resolve()):
            return 0
    except Exception:
        return 0

    try:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    except Exception as e:
        if log_fn:
            log_fn(f"[WARN] 清理 onnxruntime 孤儿目录失败: {e}")
        return 0

    if log_fn:
        log_fn(f"[INFO] 已清理未被 pip 管理的 onnxruntime 残留目录: {target}")
    return 1


def _verify_runtime_support_imports(pyexe: str, timeout: int = 30) -> tuple[bool, str]:
    """Verify core imports that ONNX Runtime relies on after pip repair."""
    code = (
        "import importlib, json, traceback\n"
        f"mods = {json.dumps(RUNTIME_IMPORT_CHECKS, ensure_ascii=False)}\n"
        "bad = []\n"
        "for pkg, mod in mods.items():\n"
        " try:\n"
        "  importlib.import_module(mod)\n"
        " except BaseException as e:\n"
        "  bad.append({'pkg': pkg, 'module': mod, 'err': f'{type(e).__name__}: {e}', 'traceback': traceback.format_exc()[-1200:]})\n"
        "print(json.dumps({'ok': not bad, 'bad': bad}, ensure_ascii=False))\n"
    )
    try:
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        result = subprocess.run(
            [str(pyexe), "-c", code],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        raw = "\n".join([(result.stdout or ""), (result.stderr or "")]).strip()
        payload = None
        for line in reversed(raw.splitlines()):
            s = line.strip()
            if s.startswith("{") and s.endswith("}"):
                try:
                    payload = json.loads(s)
                    break
                except Exception:
                    pass
        if not isinstance(payload, dict):
            return False, f"runtime dependency check no json output: {raw[:400]}"
        if payload.get("ok"):
            return True, ""
        bad = payload.get("bad") or []
        if bad:
            first = bad[0]
            return False, f"{first.get('pkg')}: {first.get('err') or 'unknown'}"
        return False, "runtime dependency check failed: unknown"
    except subprocess.TimeoutExpired:
        return False, "runtime dependency check timeout"
    except Exception as e:
        return False, str(e)


def _force_repair_broken_runtime_imports(
    pyexe: str,
    log_fn=None,
    use_mirror: bool = False,
    max_rounds: int = 4,
) -> tuple[bool, str]:
    """Force-reinstall only the runtime support package whose import is actually broken."""
    last_err = ""
    for _ in range(max_rounds):
        ok, err = _verify_runtime_support_imports(pyexe)
        if ok:
            return True, ""
        last_err = err
        pkg = (err.split(":", 1)[0] if err else "").strip().lower()
        spec = CRITICAL_VERSIONS.get(pkg)
        if not spec:
            return False, err

        if log_fn:
            log_fn(f"  [WARN] {pkg} 导入失败，定点强制修复: {err[:240]}")
        cmd = [
            str(pyexe),
            "-m",
            "pip",
            "install",
            spec,
            "--upgrade",
            "--force-reinstall",
            "--no-deps",
            *PIP_INSTALL_SUPPRESS_ARGS,
        ]
        if use_mirror:
            cmd += ["-i", "https://pypi.tuna.tsinghua.edu.cn/simple"]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=240,
                creationflags=flags,
            )
            if result.returncode != 0:
                raw = (result.stderr or result.stdout or "").strip().replace("\r", "")
                if log_fn:
                    log_fn(f"  [WARN] 强制修复 {pkg} 失败: {raw[:400]}")
                return False, raw[:400] or err
            if log_fn:
                log_fn(f"  [OK] 已强制修复 {pkg}")
        except subprocess.TimeoutExpired:
            return False, f"{pkg} force repair timeout"
        except Exception as e:
            return False, str(e)

    ok, err = _verify_runtime_support_imports(pyexe)
    return ok, err or last_err


def _fix_critical_versions(pyexe: str, log_fn=None, use_mirror: bool = False) -> bool:
    """Force critical dependency versions after installation."""
    import subprocess

    if log_fn:
        log_fn("[INFO] 正在修复关键依赖版本...")

    _cleanup_pip_interrupted_leftovers(pyexe, log_fn)

    installed_before = _current_installed(pyexe)

    for pkg, spec in CRITICAL_VERSIONS.items():
        try:
            cur = installed_before.get(pkg)
            if cur and _version_satisfies_spec(pkg, cur, spec):
                continue

            cmd = [str(pyexe), "-m", "pip", "install", spec, "--upgrade", "--no-deps", *PIP_INSTALL_SUPPRESS_ARGS]
            if use_mirror:
                cmd += ["-i", "https://pypi.tuna.tsinghua.edu.cn/simple"]
            timeout_sec = 180
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec, creationflags=flags)
            if log_fn:
                if result.returncode == 0:
                    log_fn(f"  [OK] 已修复 {pkg} → {spec.split('==')[-1] if '==' in spec else spec}")
                else:
                    err = (result.stderr or result.stdout or "").strip().replace("\r", "")
                    log_fn(f"  [WARN] 修复 {pkg} 失败: {err[:240]}")
        except subprocess.TimeoutExpired:
            if log_fn:
                log_fn(f"  [WARN] 修复 {pkg} 超时，已跳过")
        except Exception as e:
            if log_fn:
                log_fn(f"  [WARN] 修复 {pkg} 异常: {e}")

    if log_fn:
        log_fn("[INFO] 关键版本修复完成")

    ok, err = _verify_runtime_support_imports(pyexe)
    if not ok:
        ok, err = _force_repair_broken_runtime_imports(
            pyexe,
            log_fn=log_fn,
            use_mirror=use_mirror,
        )
    if log_fn:
        if ok:
            log_fn("[OK] ONNX Runtime 支撑依赖导入检查通过（numpy/protobuf 等）")
        else:
            log_fn(f"[WARN] ONNX Runtime 关键依赖仍不可用: {err[:400]}")
    return ok


_CORE_VERIFY_CODE = """
import importlib.util

for mod in ("transformers", "rapidocr", "cv2", "PIL", "latex2mathml.converter", "matplotlib", "fitz"):
    if importlib.util.find_spec(mod) is None:
        raise RuntimeError(f"{mod} not installed")

print("CORE OK")
"""


def _onnxruntime_session_verify_code(*, expect_gpu: bool) -> str:
    expected_provider = "CUDAExecutionProvider" if expect_gpu else "CPUExecutionProvider"
    requested_providers = (
        "['CUDAExecutionProvider', 'CPUExecutionProvider']"
        if expect_gpu
        else "['CPUExecutionProvider']"
    )
    layer_name = "MATHCRAFT_GPU" if expect_gpu else "MATHCRAFT_CPU"
    return f"""
import onnxruntime as ort


def _varint(value):
    out = []
    value = int(value)
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            break
    return bytes(out)


def _key(field, wire_type):
    return _varint((int(field) << 3) | int(wire_type))


def _int_field(field, value):
    return _key(field, 0) + _varint(value)


def _str_field(field, value):
    raw = str(value).encode("utf-8")
    return _key(field, 2) + _varint(len(raw)) + raw


def _msg_field(field, payload):
    return _key(field, 2) + _varint(len(payload)) + payload


def _minimal_identity_onnx():
    dim = _int_field(1, 1)
    shape = _msg_field(1, dim)
    tensor_type = _int_field(1, 1) + _msg_field(2, shape)
    type_proto = _msg_field(1, tensor_type)
    value_x = _str_field(1, "x") + _msg_field(2, type_proto)
    value_y = _str_field(1, "y") + _msg_field(2, type_proto)
    node = _str_field(1, "x") + _str_field(2, "y") + _str_field(4, "Identity")
    graph = _msg_field(1, node) + _str_field(2, "g") + _msg_field(11, value_x) + _msg_field(12, value_y)
    opset = _int_field(2, 13)
    return _int_field(1, 8) + _str_field(2, "latexsnipper-check") + _msg_field(7, graph) + _msg_field(8, opset)


providers = list(ort.get_available_providers() or [])
expected = "{expected_provider}"
if expected not in providers:
    raise RuntimeError(f"{{expected}} unavailable: {{providers}}")

session = ort.InferenceSession(_minimal_identity_onnx(), providers={requested_providers})
actual = list(session.get_providers() or [])
if expected not in actual:
    raise RuntimeError(
        f"{{expected}} listed but failed to initialize an ONNX session; "
        f"available={{providers}}, session={{actual}}"
    )

print("ONNX providers:", providers)
print("ONNX session providers:", actual)
print("{layer_name} OK")
"""


LAYER_VERIFY_CODE = {
    "BASIC": """
import PIL
import requests
import lxml
print("BASIC OK")
""",
    "CORE": _CORE_VERIFY_CODE,
    "MATHCRAFT_CPU": _onnxruntime_session_verify_code(expect_gpu=False),
    "MATHCRAFT_GPU": _onnxruntime_session_verify_code(expect_gpu=True),
    "PANDOC": """
import importlib.util, shutil, os, sys
if importlib.util.find_spec("pypandoc") is None:
    raise RuntimeError("pypandoc not installed")
configured_pandoc = None
try:
    import json
    from pathlib import Path
    cfg_path = Path.home() / ".latexsnipper" / "LaTeXSnipper_config.json"
    if cfg_path.exists():
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        raw = str(cfg.get("pandoc_executable_path", "") or "").strip() if isinstance(cfg, dict) else ""
        if raw:
            path = Path(raw).expanduser()
            configured_pandoc = path if path.is_file() else None
except Exception:
    configured_pandoc = None
if configured_pandoc is not None:
    deps_dir = str(configured_pandoc.parent)
    if deps_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = deps_dir + os.pathsep + os.environ.get("PATH", "")
# Also check deps/pandoc.
deps_pandoc = os.path.join(os.path.dirname(sys.executable), "pandoc")
if os.path.isdir(deps_pandoc) and deps_pandoc not in os.environ.get("PATH", ""):
    os.environ["PATH"] = deps_pandoc + os.pathsep + os.environ.get("PATH", "")
if not shutil.which("pandoc"):
    raise RuntimeError("pandoc binary not found (pypandoc is installed but pandoc executable is missing)")
print("PANDOC OK")
""",
}


def _verify_layer_runtime(pyexe: str, layer: str, timeout: int = 60) -> tuple:
    """Verify whether a feature layer works at runtime."""
    import subprocess

    if layer == "CORE":
        timeout = max(timeout, 120)

    if layer in LAYER_VERIFY_CODE:
        code = LAYER_VERIFY_CODE[layer]
    else:

        return True, ""

    try:
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        result = subprocess.run(
            [pyexe, "-c", code],
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )
        if result.returncode == 0:
            return True, ""
        else:

            err = (result.stderr or result.stdout or "").strip()
            if not err:
                err = f"验证进程返回码 {result.returncode}，但无可用输出"

            err_lines = err.replace("\r", "").split('\n')[-15:]
            return False, '\n'.join(err_lines)
    except subprocess.TimeoutExpired:
        return False, "验证超时"
    except Exception as e:
        return False, str(e)


def _layer_verify_failure_diagnostics(layer: str) -> list[str]:
    if layer != "MATHCRAFT_GPU":
        return []
    try:
        from backend.cuda_diagnostics import diagnose_cuda_dll_paths

        report = diagnose_cuda_dll_paths()
        return [report.format_for_user(), report.format_for_log()]
    except Exception as e:
        return [f"CUDA/cuDNN DLL 诊断失败: {e}"]


def _verify_installed_layers(pyexe: str, claimed_layers: list, log_fn=None) -> list:
    """Verify all installed layers and return the layers that pass."""
    verified = []
    for layer in claimed_layers:
        ok, err = _verify_layer_runtime(pyexe, layer)
        if ok:
            verified.append(layer)
            if log_fn:
                log_fn(f"[OK] {layer} 层验证通过")
        else:
            if log_fn:
                log_fn(f"[WARN] {layer} 层验证失败: {err[:200]}")
                for diag_line in _layer_verify_failure_diagnostics(layer):
                    log_fn(f"[DIAG] {diag_line}")
    return verified


def _verify_onnxruntime_runtime(pyexe: str, expect_gpu: bool = False, timeout: int = 30) -> tuple[bool, str]:
    """Verify that ONNX Runtime imports and exposes the expected backend."""
    code = (
        "import json, traceback\n"
        "out = {'ok': False, 'file': '', 'has_func': False, 'providers': [], 'err': ''}\n"
        "try:\n"
        " import onnxruntime as ort\n"
        " out['file'] = str(getattr(ort, '__file__', '') or '')\n"
        " out['has_func'] = bool(hasattr(ort, 'get_available_providers'))\n"
        " if out['has_func']:\n"
        "  out['providers'] = list(ort.get_available_providers() or [])\n"
        " out['ok'] = True\n"
        "except BaseException as e:\n"
        " out['err'] = f'{type(e).__name__}: {e}'\n"
        " out['traceback'] = traceback.format_exc()[-1600:]\n"
        "print(json.dumps(out, ensure_ascii=False))\n"
    )
    try:
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        result = subprocess.run(
            [str(pyexe), "-c", code],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        raw = "\n".join([(result.stdout or ""), (result.stderr or "")]).strip()
        payload = None
        for line in reversed(raw.splitlines()):
            s = line.strip()
            if not s:
                continue
            if s.startswith("{") and s.endswith("}"):
                try:
                    payload = json.loads(s)
                    break
                except Exception:
                    pass
        if not isinstance(payload, dict):
            return False, f"onnxruntime check no json output: {raw[:240]}"
        if not payload.get("ok"):
            detail = payload.get("err") or payload.get("traceback") or "unknown"
            return False, f"onnxruntime import failed: {str(detail)[:400]}"
        if not payload.get("has_func"):
            return False, "onnxruntime missing get_available_providers (broken namespace package)"
        providers = payload.get("providers") or []
        if expect_gpu and "CUDAExecutionProvider" not in providers:
            return False, f"CUDAExecutionProvider unavailable: {providers}"
        if not expect_gpu and "CPUExecutionProvider" not in providers:
            return False, f"CPUExecutionProvider unavailable: {providers}"
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "onnxruntime check timeout"
    except Exception as e:
        return False, str(e)


def _uninstall_package_if_present(pyexe: str, pkg_name: str, installed_map: dict | None = None,
                                  log_fn=None, timeout: int = 120) -> bool:
    pkg_key = str(pkg_name or "").strip().lower()
    if not pkg_key:
        return False
    current = installed_map if installed_map is not None else _current_installed(pyexe)
    if pkg_key not in current:
        if pkg_key in {"onnxruntime", "onnxruntime-gpu"}:
            return _cleanup_orphan_onnxruntime_namespace(
                pyexe,
                installed_map=current,
                log_fn=log_fn,
            ) > 0
        return False
    try:
        subprocess.run(
            [str(pyexe), "-m", "pip", "uninstall", pkg_key, "-y"],
            timeout=timeout,
            check=False,
            creationflags=flags
        )
        current.pop(pkg_key, None)
        if pkg_key in {"onnxruntime", "onnxruntime-gpu"}:
            _cleanup_orphan_onnxruntime_namespace(
                pyexe,
                installed_map=current,
                log_fn=log_fn,
            )
        if log_fn:
            log_fn(f"[OK] 已卸载冲突的 {pkg_key} ✅")
        return True
    except Exception as e:
        if log_fn:
            log_fn(f"[WARN] 卸载 {pkg_key} 失败（继续后续修复）: {e}")
        return False


def _repair_gpu_onnxruntime_runtime(pyexe: str, ort_gpu_spec: str, stop_event, pause_event, log_q,
                                    use_mirror: bool = False, force_reinstall: bool = False,
                                    no_cache: bool = False, proc_setter=None) -> tuple[bool, str]:
    installed_now = _current_installed(pyexe)
    if "onnxruntime" in installed_now:
        log_q.put("[INFO] 检测到 onnxruntime（CPU）被后续依赖重新带入，正在移除以避免覆盖 GPU providers...")
        log_q.put("[INFO] 注意：onnxruntime 和 onnxruntime-gpu 不能同时存在！")
        _uninstall_package_if_present(
            pyexe,
            "onnxruntime",
            installed_map=installed_now,
            log_fn=log_q.put,
        )

    ort_ok, ort_err = _verify_onnxruntime_runtime(pyexe, expect_gpu=True, timeout=45)
    if ort_ok:
        return True, ""

    log_q.put(f"[WARN] onnxruntime-gpu 运行时异常，先修复 ONNX 关键依赖链: {ort_err}")
    _fix_critical_versions(pyexe, log_q.put, use_mirror=use_mirror)

    ort_ok_after_deps, ort_err_after_deps = _verify_onnxruntime_runtime(
        pyexe, expect_gpu=True, timeout=45
    )
    if ort_ok_after_deps:
        return True, ""

    log_q.put(f"[WARN] ONNX 关键依赖修复后仍异常，刷新 onnxruntime-gpu 本体: {ort_err_after_deps}")
    repaired = _pip_install(
        pyexe,
        ort_gpu_spec,
        stop_event,
        log_q,
        use_mirror=use_mirror,
        flags=flags,
        pause_event=pause_event,
        force_reinstall=False,
        no_cache=no_cache,
        proc_setter=proc_setter,
    )
    if not repaired:
        return False, ort_err_after_deps or ort_err

    ort_ok2, ort_err2 = _verify_onnxruntime_runtime(pyexe, expect_gpu=True, timeout=45)
    return ort_ok2, (ort_err2 or ort_err_after_deps or ort_err)


def _current_installed(pyexe):
    """Return installed packages for the current environment."""
    def _installed_via_metadata() -> dict:
        """
        Fallback path when pip is unavailable/broken:
        query installed distributions via importlib.metadata.
        """
        code = (
            "import json\n"
            "try:\n"
            "  from importlib import metadata as _md\n"
            "except Exception:\n"
            "  import importlib_metadata as _md\n"
            "out = {}\n"
            "for d in _md.distributions():\n"
            "  try:\n"
            "    n = (d.metadata.get('Name') or '').strip().lower()\n"
            "  except Exception:\n"
            "    n = ''\n"
            "  if not n:\n"
            "    continue\n"
            "  try:\n"
            "    v = (d.version or '').strip()\n"
            "  except Exception:\n"
            "    v = ''\n"
            "  out[n] = v\n"
            "print(json.dumps(out, ensure_ascii=False))\n"
        )
        try:
            with subprocess_lock:
                out = subprocess.check_output(
                    [str(pyexe), "-c", code],
                    text=True,
                    creationflags=flags,
                )
            payload = (out or "").strip()
            if not payload:
                return {}
            data = json.loads(payload)
            if isinstance(data, dict):
                print(f"[DEBUG] 已安装包数量(元数据回退): {len(data)}")
                return {str(k).lower(): str(v) for k, v in data.items()}
        except Exception as e:
            print(f"[WARN] importlib.metadata 回退失败: {e}")
        return {}

    try:
        with subprocess_lock:
            subprocess.check_call([str(pyexe), "-m", "pip", "--version"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    except Exception as e:
        print(f"[WARN] pip 不可用，使用元数据回退: {e}")
        return _installed_via_metadata()
    try:
        with subprocess_lock:
            out = subprocess.check_output(
                [str(pyexe), "-m", "pip", "list", "--disable-pip-version-check", "--format=json"],
                text=True, creationflags=flags)
        raw = (out or "").strip()
        data = None
        try:
            data = json.loads(raw)
        except Exception:
            # Robust parse for rare noisy stdout cases.
            left_idx = raw.find("[")
            right_idx = raw.rfind("]")
            if left_idx != -1 and right_idx != -1 and right_idx >= left_idx:
                data = json.loads(raw[left_idx:right_idx + 1])
            else:
                raise
        result = {d["name"].lower(): d["version"] for d in data}
        if not result:
            print("[WARN] pip list 返回 0 个包，使用元数据回退二次确认。")
            metadata_installed = _installed_via_metadata()
            if metadata_installed:
                return metadata_installed
        print(f"[DEBUG] 已安装包数量: {len(result)}")
        return result
    except Exception as e:
        print(f"[WARN] 获取已安装包列表失败，使用元数据回退: {e}")
        return _installed_via_metadata()


def _pip_install(pyexe, pkg, stop_event, log_q, use_mirror=False, flags=0, pause_event=None,
                 force_reinstall=False, no_cache=False, proc_setter=None):
    """Install one dependency package with live logs, mirrors, retries, and nonblocking output."""
    return PipInstallRunner(
        pyexe=pyexe,
        pkg=pkg,
        stop_event=stop_event,
        log_q=log_q,
        use_mirror=use_mirror,
        flags=flags,
        pause_event=pause_event,
        force_reinstall=force_reinstall,
        no_cache=no_cache,
        proc_setter=proc_setter,
        pip_ready_event=pip_ready_event,
        suppress_args=PIP_INSTALL_SUPPRESS_ARGS,
        safe_run=safe_run,
        subprocess_lock=subprocess_lock,
        onnxruntime_gpu_policy=onnxruntime_gpu_policy,
        cleanup_orphan_onnxruntime_namespace=_cleanup_orphan_onnxruntime_namespace,
        diagnose_install_failure=_diagnose_install_failure,
    ).install()
