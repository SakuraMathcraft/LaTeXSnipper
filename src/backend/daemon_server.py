import argparse
import base64
import builtins
import io
import queue
import json
import os
import re
import subprocess
import socketserver
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path
from typing import Any

from PIL import Image

from backend.model import ModelWrapper
from backend.latex_export_formats import build_export_formats
from backend.torch_runtime import TORCH_CPU_PLAN, TORCH_CUDA_MATRIX, detect_torch_gpu_plan, detect_torch_info
from backend.rpc_contract import (
    CONTRACT_NAME,
    CONTRACT_VERSION,
    METHODS,
    METHOD_HEALTH,
    METHOD_MODEL_STATUS,
    METHOD_PREDICT_IMAGE,
    METHOD_SHUTDOWN,
    METHOD_TASK_CANCEL,
    METHOD_TASK_STATUS,
    METHOD_TASK_SUBMIT,
    METHOD_WARMUP,
    TASK_KIND_PREDICT_IMAGE,
    TASK_KIND_PREDICT_PDF,
    TASK_KIND_INSTALL_DEPS,
    TASK_KIND_SWITCH_CPU_GPU,
    TASK_STATUS_CANCELLED,
    TASK_STATUS_ERROR,
    TASK_STATUS_QUEUED,
    TASK_STATUS_RUNNING,
    TASK_STATUS_SUCCESS,
    is_known_method,
    is_supported_task_kind,
)

PIP_INDEX_OFFICIAL = "https://pypi.org/simple"
PIP_INDEX_TUNA = "https://pypi.tuna.tsinghua.edu.cn/simple"
TORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"
ORT_GPU_SPEC_BY_TAG = {
    "cu118": "onnxruntime-gpu~=1.18.1",
}
ORT_GPU_SPEC_DEFAULT = "onnxruntime-gpu~=1.19.2"

LAYER_SPECS: dict[str, list[str]] = {
    "BASIC": [
        "simsimd~=6.0.5",
        "lxml~=4.9.3",
        "pillow~=11.0.0",
        "pyperclip~=1.11.0",
        "packaging~=25.0",
        "requests~=2.32.5",
        "tqdm~=4.67.1",
        "numpy>=1.26.4",
        "filelock~=3.13.1",
        "pydantic~=2.9.2",
        "regex~=2024.9.11",
        "safetensors~=0.6.2",
        "sentencepiece~=0.1.99",
        "certifi~=2024.2.2",
        "idna~=3.6",
        "urllib3~=2.5.0",
        "colorama~=0.4.6",
        "psutil~=7.1.0",
        "typing_extensions>=4.12.2",
    ],
    "CORE": [
        "transformers==4.55.4",
        "tokenizers==0.21.4",
        "optimum-onnx>=0.0.3",
        "pix2text==1.1.6",
        "protobuf>=3.20,<5",
        "latex2mathml>=2.0.0",
        "matplotlib~=3.8.4",
        "pymupdf~=1.23.0",
    ],
}


def _to_markdown_from_latex(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    return f"$$\n{raw}\n$$\n"


def _to_latex_from_markdown(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    return re.sub(r"^\s*\$\$\s*|\s*\$\$\s*$", "", raw, flags=re.S).strip()


def _looks_like_single_formula(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    if len(raw) > 4000:
        return False
    if "\n\n---\n\n" in raw or "\n\n% --- Page ---\n\n" in raw:
        return False
    if "\n" in raw and not raw.startswith("$$"):
        return False
    return True


def _json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    return str(value)


def _ensure_utf8_stdio() -> None:
    # 强制 daemon 进程的标准流使用 UTF-8，避免 Windows 默认代码页导致编码异常。
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        try:
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="backslashreplace")
        except Exception:
            pass


_ensure_utf8_stdio()


def _log_event(event: str, **fields: Any) -> None:
    payload = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
        "event": str(event),
    }
    payload.update({str(k): _json_safe(v) for k, v in fields.items()})
    _safe_stdout_line(f"[DAEMON_EVT] {json.dumps(payload, ensure_ascii=False)}")


def _safe_stdout_line(text: str) -> None:
    s = str(text if text is not None else "")
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    data = (s + "\n").encode(enc, errors="backslashreplace")
    try:
        buf = getattr(sys.stdout, "buffer", None)
        if buf is not None:
            buf.write(data)
            buf.flush()
        else:
            sys.stdout.write(data.decode(enc, errors="ignore"))
            sys.stdout.flush()
    except Exception:
        try:
            print(s.encode("ascii", errors="backslashreplace").decode("ascii"), flush=True)
        except Exception:
            pass


def _build_safe_print(original_print):
    def _safe_print(*args, **kwargs):
        try:
            sep = kwargs.get("sep", " ")
            end = kwargs.get("end", "\n")
            msg = sep.join(str(x) for x in args)
            if isinstance(end, str) and end not in ("", "\n", "\r\n"):
                msg = f"{msg}{end.rstrip()}"
            _safe_stdout_line(msg)
            return
        except Exception:
            pass
        try:
            original_print(*args, **kwargs)
        except Exception:
            pass

    return _safe_print


def _error_payload(e: Exception, *, include_trace: bool = False) -> dict[str, Any]:
    out = {
        "ok": False,
        "error": str(e),
        "error_type": e.__class__.__name__,
    }
    if include_trace:
        out["traceback"] = traceback.format_exc(limit=6)
    return out


def _error_response(error: str, *, error_type: str = "RuntimeError", error_code: str = "", details: dict[str, Any] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "ok": False,
        "error": str(error or "unknown error"),
        "error_type": str(error_type or "RuntimeError"),
    }
    if error_code:
        out["error_code"] = str(error_code)
    if details:
        out["details"] = _json_safe(details)
    return out


class RpcTaskError(RuntimeError):
    def __init__(self, message: str, *, error_code: str = "TASK_RUNTIME_ERROR", details: dict[str, Any] | None = None):
        super().__init__(message)
        self.error_code = str(error_code or "TASK_RUNTIME_ERROR")
        self.details = details or {}


class _State:
    def __init__(self, model_name: str, token: str, wrapper: Any | None = None):
        self._model_name = str(model_name or "pix2text")
        self.wrapper = wrapper if wrapper is not None else None
        self.token = token or ""
        self.wrapper_lock = threading.RLock()
        self.task_lock = threading.Lock()
        self.task_queue: queue.Queue[str | None] = queue.Queue()
        self.tasks: dict[str, dict[str, Any]] = {}
        self._stop_event = threading.Event()
        self.server_ref = None
        self.task_worker = threading.Thread(target=self._task_worker_loop, daemon=True)
        self.task_worker.start()
        if self.wrapper is not None:
            _log_event("wrapper_initialized", model=self._model_name, pid=os.getpid(), eager=True)
        else:
            _log_event("wrapper_deferred", model=self._model_name, pid=os.getpid())

    def _ensure_wrapper(self) -> ModelWrapper:
        with self.wrapper_lock:
            if self.wrapper is None:
                self.wrapper = ModelWrapper(self._model_name)
                _log_event("wrapper_initialized", model=self._model_name, pid=os.getpid(), eager=False)
            return self.wrapper

    def _task_snapshot(self, task: dict[str, Any]) -> dict[str, Any]:
        return {
            "task_id": str(task.get("task_id", "")),
            "kind": str(task.get("kind", "")),
            "status": str(task.get("status", "")),
            "created_at": float(task.get("created_at", 0.0) or 0.0),
            "started_at": float(task.get("started_at", 0.0) or 0.0),
            "ended_at": float(task.get("ended_at", 0.0) or 0.0),
            "progress_current": int(task.get("progress_current", 0) or 0),
            "progress_total": int(task.get("progress_total", 0) or 0),
            "error": str(task.get("error", "") or ""),
            "error_type": str(task.get("error_type", "") or ""),
            "error_code": str(task.get("error_code", "") or ""),
            "details": _json_safe(task.get("details", {})),
            "output": _json_safe(task.get("output", {})),
            "cancel_requested": bool(task.get("cancel_requested", False)),
        }

    def _task_create(self, kind: str, params: dict[str, Any]) -> str:
        task_id = uuid.uuid4().hex
        rec = {
            "task_id": task_id,
            "kind": str(kind or ""),
            "params": dict(params or {}),
            "status": TASK_STATUS_QUEUED,
            "created_at": time.time(),
            "started_at": 0.0,
            "ended_at": 0.0,
            "progress_current": 0,
            "progress_total": 0,
            "error": "",
            "error_type": "",
            "error_code": "",
            "details": {},
            "output": {},
            "cancel_requested": False,
        }
        with self.task_lock:
            self.tasks[task_id] = rec
        self.task_queue.put(task_id)
        _log_event("task_queued", task_id=task_id, kind=kind)
        return task_id

    def _task_get(self, task_id: str) -> dict[str, Any] | None:
        with self.task_lock:
            rec = self.tasks.get(task_id)
            return dict(rec) if rec else None

    def _task_update(self, task_id: str, **fields: Any) -> dict[str, Any] | None:
        with self.task_lock:
            rec = self.tasks.get(task_id)
            if not rec:
                return None
            rec.update(fields)
            return dict(rec)

    def _task_merge_details(self, task_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        with self.task_lock:
            rec = self.tasks.get(task_id)
            if not rec:
                return None
            details = rec.get("details", {})
            if not isinstance(details, dict):
                details = {}
            merged = dict(details)
            merged.update(_json_safe(patch or {}))
            rec["details"] = merged
            return dict(rec)

    def _task_set_progress(self, task_id: str, current: int, total: int) -> None:
        rec = self._task_update(
            task_id,
            progress_current=max(int(current), 0),
            progress_total=max(int(total), 0),
        )
        if rec:
            _log_event(
                "task_progress",
                task_id=task_id,
                kind=str(rec.get("kind", "") or ""),
                progress_current=int(rec.get("progress_current", 0) or 0),
                progress_total=int(rec.get("progress_total", 0) or 0),
                status=str(rec.get("status", "") or ""),
            )

    def _task_should_cancel(self, task_id: str) -> bool:
        with self.task_lock:
            rec = self.tasks.get(task_id) or {}
            return bool(rec.get("cancel_requested", False))

    def _subprocess_flags(self) -> int:
        if os.name != "nt":
            return 0
        return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def _processes_using_python(self, pyexe: str) -> list[dict[str, Any]]:
        target = str(Path(pyexe).resolve()).lower()
        target_dir = str(Path(target).parent).lower()
        target_pythonw = str((Path(target_dir) / "pythonw.exe").resolve()).lower() if os.name == "nt" else ""
        alias_targets = {target}
        if target_pythonw:
            alias_targets.add(target_pythonw)
        out: list[dict[str, Any]] = []
        try:
            import psutil  # type: ignore

            for p in psutil.process_iter(["pid", "name", "exe", "cmdline"]):
                try:
                    info = p.info or {}
                    pid = int(info.get("pid") or 0)
                    if pid <= 0 or pid == os.getpid():
                        continue
                    exe = str(info.get("exe") or "").strip()
                    cmdline = info.get("cmdline") or []
                    cmdline_text = " ".join(str(x) for x in cmdline[:12]).strip()
                    cmdline_lc = cmdline_text.lower()
                    exe_match = False
                    if exe:
                        try:
                            exe_match = str(Path(exe).resolve()).lower() in alias_targets
                        except Exception:
                            exe_match = str(exe).strip().lower() in alias_targets
                    cmdline_match = target in cmdline_lc or (target_pythonw and target_pythonw in cmdline_lc)
                    if not exe_match and not cmdline_match:
                        continue
                    out.append(
                        {
                            "pid": pid,
                            "name": str(info.get("name") or ""),
                            "exe": exe,
                            "cmdline": cmdline_text,
                        }
                    )
                except Exception:
                    continue
        except Exception:
            return []
        return out

    def _site_packages_from_python(self, pyexe: str) -> Path:
        py = Path(pyexe)
        base = py.parent if py.name.lower() == "python.exe" else py
        if base.name.lower() == "scripts":
            base = base.parent
        primary = base / "Lib" / "site-packages"
        if primary.exists():
            return primary
        return py.parent / "Lib" / "site-packages"

    def _cleanup_torch_tilde_leftovers(self, pyexe: str) -> list[str]:
        site = self._site_packages_from_python(pyexe)
        removed: list[str] = []
        if not site.exists():
            return removed
        for p in site.glob("~orch*"):
            try:
                if p.is_dir():
                    for sub in sorted(p.rglob("*"), reverse=True):
                        try:
                            if sub.is_file() or sub.is_symlink():
                                sub.unlink(missing_ok=True)
                            else:
                                sub.rmdir()
                        except Exception:
                            pass
                    p.rmdir()
                else:
                    p.unlink(missing_ok=True)
                removed.append(str(p))
            except Exception:
                continue
        if removed:
            _safe_stdout_line(f"[DAEMON_DEPS] cleaned invalid torch leftovers: {len(removed)}")
        return removed

    def _classify_install_failure(self, lines: list[str]) -> tuple[str, str]:
        key_flags = ("[FATAL]", "[ERR]", "[FAIL]", "Traceback", "RuntimeError", "ERROR")
        primary = ""
        for line in reversed(lines):
            if any(flag in line for flag in key_flags):
                primary = line
                break
        if not primary and lines:
            primary = lines[-1]
        if not primary:
            primary = "unknown install failure"

        text = "\n".join(lines).lower()
        if ("winerror 5" in text) or ("拒绝访问" in text) or ("access is denied" in text):
            return primary, "ENV_FILE_LOCKED"
        if "daemon runtime already loaded torch stack" in text:
            return primary, "DAEMON_ENV_LOCKED"
        if "target python is in use by other processes" in text:
            return primary, "ENV_IN_USE"
        if "no module named 'torchvision'" in text:
            return primary, "TORCHVISION_MISSING"
        return primary, "TASK_RUNTIME_ERROR"

    def _normalize_layers(self, layers_raw: Any) -> list[str]:
        if isinstance(layers_raw, (list, tuple, set)):
            items = [str(x).strip().upper() for x in layers_raw if str(x).strip()]
        elif isinstance(layers_raw, str):
            items = [x.strip().upper() for x in layers_raw.split(",") if x.strip()]
        else:
            items = []
        if not items:
            items = ["BASIC", "CORE"]

        known = {"BASIC", "CORE", "HEAVY_CPU", "HEAVY_GPU"}
        layers: list[str] = []
        unknown: list[str] = []
        for x in items:
            if x in known and x not in layers:
                layers.append(x)
            elif x not in known and x not in unknown:
                unknown.append(x)
        if unknown:
            raise RpcTaskError(
                "unknown layer(s)",
                error_code="RPC_INVALID_PARAMS",
                details={"unknown_layers": unknown, "known_layers": sorted(known)},
            )
        return layers

    def _use_mirror(self, mirror: str) -> bool:
        m = (mirror or "").strip().lower()
        return m in {"1", "true", "yes", "on", "mirror", "tuna", "tsinghua", "cn"}

    def _pip_source_args(self, use_mirror: bool) -> list[str]:
        idx = PIP_INDEX_TUNA if use_mirror else PIP_INDEX_OFFICIAL
        return ["-i", idx]

    def _pip_install_base(self, pyexe: str) -> list[str]:
        return [
            pyexe,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "--default-timeout",
            "180",
            "--retries",
            "5",
            "--prefer-binary",
        ]

    def _resolve_python_for_deps(self, deps_dir: str) -> tuple[str, str]:
        dep = (deps_dir or "").strip()
        if dep:
            d = Path(dep)
            candidates = [
                d / "python311" / "python.exe",
                d / "python.exe",
                d / "Scripts" / "python.exe",
                d / "venv" / "Scripts" / "python.exe",
                d / ".venv" / "Scripts" / "python.exe",
            ]
            for c in candidates:
                if c.exists():
                    return str(c), str(d)
            raise RpcTaskError(
                "deps_dir does not contain a usable python.exe",
                error_code="RPC_INVALID_PARAMS",
                details={"deps_dir": dep},
            )

        env_pyexe = str(os.environ.get("LATEXSNIPPER_PYEXE", "") or "").strip()
        if env_pyexe and os.path.exists(env_pyexe):
            py = Path(env_pyexe)
        else:
            py = Path(sys.executable)
        if not py.exists():
            raise RpcTaskError(
                "python.exe not found",
                error_code="TASK_RUNTIME_ERROR",
                details={"python": str(py)},
            )

        if py.parent.name.lower() == "python311":
            d = py.parent.parent
        elif py.parent.name.lower() == "scripts":
            d = py.parent.parent
        else:
            d = py.parent
        return str(py), str(d)

    def _deps_state_path(self, deps_dir: str) -> Path:
        return Path(deps_dir) / ".deps_state.json"

    def _read_state_layers(self, deps_dir: str) -> list[str]:
        p = self._deps_state_path(deps_dir)
        if not p.exists():
            return []
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return []
        layers = raw.get("installed_layers", [])
        if not isinstance(layers, list):
            return []
        out: list[str] = []
        for x in layers:
            s = str(x).strip().upper()
            if s in {"BASIC", "CORE", "HEAVY_CPU", "HEAVY_GPU"} and s not in out:
                out.append(s)
        if "HEAVY_CPU" in out and "HEAVY_GPU" in out:
            out.remove("HEAVY_CPU")
        return out

    def _write_state_layers(self, deps_dir: str, layers: list[str]) -> None:
        p = self._deps_state_path(deps_dir)
        p.parent.mkdir(parents=True, exist_ok=True)
        uniq: list[str] = []
        for x in layers:
            s = str(x).strip().upper()
            if s and s not in uniq:
                uniq.append(s)
        if "HEAVY_CPU" in uniq and "HEAVY_GPU" in uniq:
            uniq.remove("HEAVY_CPU")
        payload = {"installed_layers": uniq}
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _resolve_gpu_plan(self, requested_tag: str) -> tuple[str, str, str, str]:
        tag = (requested_tag or "").strip().lower()
        if tag:
            for row in TORCH_CUDA_MATRIX:
                if str(row.get("tag", "")).lower() == tag:
                    return (
                        tag,
                        str(row.get("torch", "")),
                        str(row.get("vision", "")),
                        str(row.get("audio", "")),
                    )
            raise RpcTaskError(
                "unsupported cuda_tag",
                error_code="RPC_INVALID_PARAMS",
                details={"cuda_tag": tag},
            )

        plan, note = detect_torch_gpu_plan()
        if not plan:
            raise RpcTaskError(
                "GPU plan unavailable",
                error_code="TASK_RUNTIME_ERROR",
                details={"reason": note},
            )
        return (
            str(plan.get("tag", "")),
            str(plan.get("torch", "")),
            str(plan.get("vision", "")),
            str(plan.get("audio", "")),
        )

    def _norm_pkg_name(self, name: str) -> str:
        return re.sub(r"[-_.]+", "-", (name or "").strip().lower())

    def _installed_pkg_map(self, pyexe: str) -> dict[str, str]:
        try:
            args = [pyexe, "-m", "pip", "list", "--format=json"]
            res = subprocess.run(
                args,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=45,
                creationflags=self._subprocess_flags(),
            )
            if res.returncode != 0:
                return {}
            payload = (res.stdout or "").strip()
            arr = json.loads(payload) if payload else []
            out: dict[str, str] = {}
            if isinstance(arr, list):
                for row in arr:
                    if not isinstance(row, dict):
                        continue
                    n = self._norm_pkg_name(str(row.get("name", "")))
                    v = str(row.get("version", "") or "").strip()
                    if n:
                        out[n] = v
            return out
        except Exception:
            return {}

    def _spec_satisfied(self, spec: str, installed: dict[str, str]) -> bool:
        spec_raw = str(spec or "").strip()
        if not spec_raw:
            return False
        try:
            from packaging.requirements import Requirement
            req = Requirement(spec_raw)
            name = self._norm_pkg_name(req.name)
            cur = str(installed.get(name, "") or "").strip()
            if not cur:
                return False
            if not str(req.specifier):
                return True
            return bool(req.specifier.contains(cur, prereleases=True))
        except Exception:
            base = re.split(r"[<>=!~ ]", spec_raw, 1)[0].strip()
            if not base:
                return False
            return self._norm_pkg_name(base) in installed

    def _run_step(self, task_id: str, kind: str, label: str, args: list[str], *, allow_fail: bool = False) -> bool:
        if self._task_should_cancel(task_id):
            raise RuntimeError("已取消")

        cmd = " ".join(args)
        _log_event("request_begin", method=f"{kind}:{label}")
        _safe_stdout_line(f"[DAEMON_STEP] {label}: {cmd}")

        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="ignore",
            bufsize=1,
            creationflags=self._subprocess_flags(),
        )
        line_q: queue.Queue[str | None] = queue.Queue()

        def _reader() -> None:
            try:
                if proc.stdout is not None:
                    for line in proc.stdout:
                        line_q.put(line.rstrip("\r\n"))
            except Exception:
                pass
            finally:
                line_q.put(None)

        t = threading.Thread(target=_reader, daemon=True)
        t.start()
        tail: list[str] = []
        saw_eof = False
        while True:
            if self._task_should_cancel(task_id):
                try:
                    proc.terminate()
                    proc.wait(timeout=3)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                raise RuntimeError("已取消")

            try:
                item = line_q.get(timeout=0.2)
            except queue.Empty:
                if proc.poll() is not None and saw_eof:
                    break
                continue
            if item is None:
                saw_eof = True
                if proc.poll() is not None:
                    break
                continue
            if item:
                tail.append(item)
                if len(tail) > 40:
                    tail = tail[-40:]
                _safe_stdout_line(f"[DAEMON_PIP] {item}")

        rc = int(proc.poll() or 0)
        ok = rc == 0
        _log_event("request_end", method=f"{kind}:{label}", ok=ok)
        if not ok and not allow_fail:
            raise RpcTaskError(
                f"{label} failed (rc={rc})",
                error_code="TASK_RUNTIME_ERROR",
                details={"label": label, "return_code": rc, "command": cmd, "tail": "\n".join(tail)},
            )
        return ok

    def _verify_layers_runtime(self, pyexe: str, layers: list[str]) -> None:
        if "HEAVY_GPU" in layers:
            info = detect_torch_info(pyexe)
            if not info.get("present"):
                raise RpcTaskError(
                    "torch not importable after HEAVY_GPU install",
                    error_code="TASK_RUNTIME_ERROR",
                    details={"torch_info": info},
                )
            if not bool(info.get("cuda_available", False)):
                raise RpcTaskError(
                    "HEAVY_GPU verify failed: CUDA not available",
                    error_code="TASK_RUNTIME_ERROR",
                    details={"torch_info": info},
                )
        elif "HEAVY_CPU" in layers:
            info = detect_torch_info(pyexe)
            if not info.get("present"):
                raise RpcTaskError(
                    "torch not importable after HEAVY_CPU install",
                    error_code="TASK_RUNTIME_ERROR",
                    details={"torch_info": info},
                )

    def _install_layers(
        self,
        task_id: str,
        *,
        layers: list[str],
        pyexe: str,
        mirror: str,
        force_verify: bool,
        cuda_tag: str = "",
    ) -> dict[str, Any]:
        use_mirror = self._use_mirror(mirror)
        steps: list[tuple[str, list[str], bool]] = []
        normalized = [x for x in layers if x in {"BASIC", "CORE", "HEAVY_CPU", "HEAVY_GPU"}]
        installed_before = self._installed_pkg_map(pyexe)
        skipped_specs: dict[str, list[str]] = {}

        if "HEAVY_CPU" in normalized and "HEAVY_GPU" in normalized:
            raise RpcTaskError(
                "HEAVY_CPU and HEAVY_GPU are mutually exclusive",
                error_code="RPC_INVALID_PARAMS",
                details={"layers": normalized},
            )

        for layer in normalized:
            specs = list(LAYER_SPECS.get(layer, []))
            if layer in {"BASIC", "CORE"} and specs and installed_before:
                pending: list[str] = []
                skipped: list[str] = []
                for s in specs:
                    if self._spec_satisfied(s, installed_before):
                        skipped.append(s)
                    else:
                        pending.append(s)
                if skipped:
                    skipped_specs[layer] = skipped
                    _safe_stdout_line(f"[DAEMON_DEPS] skip satisfied {layer}: {', '.join(skipped)}")
                specs = pending
            if specs:
                args = self._pip_install_base(pyexe) + specs + self._pip_source_args(use_mirror)
                steps.append((f"install:{layer}", args, False))

        if "HEAVY_CPU" in normalized:
            steps.append(
                (
                    "cleanup:heavy_cpu",
                    [pyexe, "-m", "pip", "uninstall", "-y", "torch", "torchvision", "torchaudio", "onnxruntime", "onnxruntime-gpu"],
                    True,
                )
            )
            cpu = TORCH_CPU_PLAN
            torch_args = (
                self._pip_install_base(pyexe)
                + [
                    f"torch=={cpu['torch']}",
                    f"torchvision=={cpu['vision']}",
                    f"torchaudio=={cpu['audio']}",
                    "--index-url",
                    TORCH_CPU_INDEX,
                    "--extra-index-url",
                    PIP_INDEX_OFFICIAL,
                ]
            )
            steps.append(("install:torch-cpu", torch_args, False))
            ort_cpu_args = self._pip_install_base(pyexe) + ["onnxruntime~=1.19.2"] + self._pip_source_args(use_mirror)
            steps.append(("install:onnxruntime-cpu", ort_cpu_args, False))

        used_cuda_tag = ""
        if "HEAVY_GPU" in normalized:
            steps.append(
                (
                    "cleanup:heavy_gpu",
                    [pyexe, "-m", "pip", "uninstall", "-y", "torch", "torchvision", "torchaudio", "onnxruntime", "onnxruntime-gpu"],
                    True,
                )
            )
            used_cuda_tag, torch_ver, vision_ver, audio_ver = self._resolve_gpu_plan(cuda_tag)
            torch_args = (
                self._pip_install_base(pyexe)
                + [
                    f"torch=={torch_ver}",
                    f"torchvision=={vision_ver}",
                    f"torchaudio=={audio_ver}",
                    "--index-url",
                    f"https://download.pytorch.org/whl/{used_cuda_tag}",
                    "--extra-index-url",
                    PIP_INDEX_OFFICIAL,
                ]
            )
            steps.append(("install:torch-gpu", torch_args, False))
            ort_gpu_spec = ORT_GPU_SPEC_BY_TAG.get(used_cuda_tag, ORT_GPU_SPEC_DEFAULT)
            ort_gpu_args = self._pip_install_base(pyexe) + [ort_gpu_spec] + self._pip_source_args(use_mirror)
            steps.append(("install:onnxruntime-gpu", ort_gpu_args, False))

        total = max(len(steps), 1)
        self._task_set_progress(task_id, 0, total)
        if not steps:
            self._task_set_progress(task_id, 1, 1)
        done = 0
        for label, cmd, allow_fail in steps:
            ok = self._run_step(task_id, "deps", label, cmd, allow_fail=allow_fail)
            if label == "install:onnxruntime-gpu" and use_mirror and not ok:
                fallback_cmd = self._pip_install_base(pyexe) + [ORT_GPU_SPEC_BY_TAG.get(used_cuda_tag, ORT_GPU_SPEC_DEFAULT)] + ["-i", PIP_INDEX_OFFICIAL]
                self._run_step(task_id, "deps", "install:onnxruntime-gpu:fallback", fallback_cmd, allow_fail=False)
            done += 1
            self._task_set_progress(task_id, done, total)

        if force_verify or ("HEAVY_CPU" in normalized) or ("HEAVY_GPU" in normalized):
            self._verify_layers_runtime(pyexe, normalized)

        return {"layers": normalized, "cuda_tag": used_cuda_tag, "skipped": skipped_specs}

    def _auto_complete_layers(self, layers: list[str]) -> list[str]:
        out = [x for x in layers if x in {"BASIC", "CORE", "HEAVY_CPU", "HEAVY_GPU"}]
        if ("CORE" in out) and ("HEAVY_CPU" not in out) and ("HEAVY_GPU" not in out):
            plan, _ = detect_torch_gpu_plan()
            out.append("HEAVY_GPU" if plan else "HEAVY_CPU")
        uniq: list[str] = []
        for x in out:
            if x not in uniq:
                uniq.append(x)
        return uniq

    def _install_layers_via_deps_bootstrap(
        self,
        task_id: str,
        *,
        layers: list[str],
        pyexe: str,
        deps_dir: str,
        mirror: str,
        force_verify: bool,
    ) -> dict[str, Any]:
        orig_print = builtins.print
        builtins.print = _build_safe_print(orig_print)
        try:
            import deps_bootstrap as db  # type: ignore
        except Exception:
            builtins.print = orig_print
            raise

        try:
            chosen_layers = self._auto_complete_layers(layers)
            if "HEAVY_CPU" in chosen_layers and "HEAVY_GPU" in chosen_layers:
                raise RpcTaskError(
                    "HEAVY_CPU and HEAVY_GPU are mutually exclusive",
                    error_code="RPC_INVALID_PARAMS",
                    details={"layers": chosen_layers},
                )

            pkgs: list[str] = []
            for lyr in chosen_layers:
                pkgs.extend(list(db.LAYER_MAP.get(lyr, [])))

            if "HEAVY_GPU" in chosen_layers:
                filtered = []
                for p in pkgs:
                    n = re.split(r"[<>=!~ ]", str(p), 1)[0].strip().lower()
                    if n == "onnxruntime":
                        continue
                    filtered.append(p)
                pkgs = filtered

            pkgs = db._filter_packages(pkgs)

            # deps_bootstrap 的 _pip_install 会等待 pip_ready_event；
            # daemon 场景未走 ensure_deps 时，这个事件不会自动置位，导致所有包被“跳过”。
            pip_ready = getattr(db, "pip_ready_event", None)
            if pip_ready is not None:
                try:
                    pip_ready.clear()
                except Exception:
                    pass
            try:
                ensure_pip = getattr(db, "_ensure_pip", None)
                if callable(ensure_pip):
                    ensure_pip(str(pyexe))
            except Exception as e:
                _safe_stdout_line(f"[DAEMON_WARN] deps pip bootstrap failed: {e}")
            finally:
                if pip_ready is not None:
                    try:
                        pip_ready.set()
                    except Exception:
                        pass

            # 早失败：pip 不可用时直接给明确错误，不进入后续“全部跳过”的伪流程
            pip_probe = subprocess.run(
                [str(pyexe), "-m", "pip", "--version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=30,
                creationflags=self._subprocess_flags(),
            )
            rc = pip_probe.returncode
            if rc is None or int(rc) != 0:
                probe_msg = (pip_probe.stderr or pip_probe.stdout or "").strip()
                raise RpcTaskError(
                    "pip unavailable before dependency install",
                    error_code="TASK_RUNTIME_ERROR",
                    details={"python": str(pyexe), "pip_probe": probe_msg[:300]},
                )

            loaded_mods = [m for m in ("torch", "torchvision", "torchaudio", "onnxruntime") if m in sys.modules]
            if loaded_mods:
                raise RpcTaskError(
                    "daemon runtime already loaded torch stack; restart daemon and retry install",
                    error_code="DAEMON_ENV_LOCKED",
                    details={"loaded_modules": loaded_mods, "pid": os.getpid()},
                )

            occupied = self._processes_using_python(str(pyexe))
            if occupied:
                raise RpcTaskError(
                    "target python is in use by other processes; close them and retry",
                    error_code="ENV_IN_USE",
                    details={"python": str(pyexe), "processes": occupied[:12]},
                )

            state_path = str(self._deps_state_path(deps_dir))
            log_q: queue.Queue[str] = queue.Queue()

            recent_lines: list[str] = []
            recent_lock = threading.Lock()
            sync_state = {"last_ts": 0.0}

            def _push_recent(line: str) -> None:
                s = str(line or "").strip()
                if not s:
                    return
                with recent_lock:
                    recent_lines.append(s)
                    if len(recent_lines) > 320:
                        del recent_lines[: len(recent_lines) - 320]
                    now = time.time()
                    force = any(
                        flag in s for flag in ("[FATAL]", "[ERR]", "[FAIL]", "Traceback", "RuntimeError", "ERROR")
                    )
                    if force or (now - float(sync_state.get("last_ts", 0.0)) >= 0.35):
                        tail_text = "\n".join(recent_lines[-120:])
                        self._task_merge_details(task_id, {"log_tail": tail_text})
                        sync_state["last_ts"] = now

            def _failure_details() -> tuple[str, str, list[str]]:
                with recent_lock:
                    lines = list(recent_lines)
                tail = lines[-80:]
                primary, code = self._classify_install_failure(lines)
                return primary, code, tail

            removed_tilde = self._cleanup_torch_tilde_leftovers(pyexe)
            if removed_tilde:
                self._task_merge_details(task_id, {"cleaned_leftovers": removed_tilde[-20:]})

            max_attempts = 2
            attempt = 1
            ok = False
            fail_primary = ""
            fail_code = "TASK_RUNTIME_ERROR"
            fail_tail: list[str] = []
            while attempt <= max_attempts:
                _push_recent(f"[INFO] install attempt {attempt}/{max_attempts}")
                stop_event = threading.Event()
                pause_event = threading.Event()
                pause_event.set()
                state_lock = threading.Lock()
                runtime_state = {"stopped": False}
                result_holder = {"ok": None}
                done_evt = threading.Event()
                cancel_watch_stop = threading.Event()

                worker = db.InstallWorker(
                    pyexe=pyexe,
                    pkgs=pkgs,
                    stop_event=stop_event,
                    pause_event=pause_event,
                    state_lock=state_lock,
                    state=runtime_state,
                    state_path=state_path,
                    chosen_layers=chosen_layers,
                    log_q=log_q,
                    mirror=self._use_mirror(mirror),
                    force_reinstall=False,
                    no_cache=False,
                )

                def _on_log(msg: str) -> None:
                    _push_recent(msg)
                    _safe_stdout_line(f"[DAEMON_DEPS] {msg}")

                def _on_progress(pct: int) -> None:
                    self._task_set_progress(task_id, int(pct or 0), 100)

                def _on_done(done_ok: bool) -> None:
                    result_holder["ok"] = bool(done_ok)
                    done_evt.set()

                worker.log_updated.connect(_on_log)
                worker.progress_updated.connect(_on_progress)
                worker.done.connect(_on_done)

                def _drain_log_q() -> None:
                    while not done_evt.is_set() or not log_q.empty():
                        try:
                            line = log_q.get(timeout=0.2)
                        except queue.Empty:
                            continue
                        if line:
                            _push_recent(line)
                            _safe_stdout_line(f"[DAEMON_PIP] {line}")

                def _watch_cancel() -> None:
                    while not cancel_watch_stop.is_set():
                        if self._task_should_cancel(task_id):
                            stop_event.set()
                            break
                        time.sleep(0.1)

                t_drain = threading.Thread(target=_drain_log_q, daemon=True)
                t_cancel = threading.Thread(target=_watch_cancel, daemon=True)
                t_drain.start()
                t_cancel.start()

                try:
                    worker.run()
                finally:
                    done_evt.set()
                    cancel_watch_stop.set()
                    try:
                        t_cancel.join(timeout=1.0)
                    except Exception:
                        pass
                    try:
                        t_drain.join(timeout=1.0)
                    except Exception:
                        pass

                if stop_event.is_set() or self._task_should_cancel(task_id):
                    raise RuntimeError("已取消")
                if result_holder["ok"] is True:
                    ok = True
                    break

                fail_primary, fail_code, fail_tail = _failure_details()
                if fail_code == "ENV_FILE_LOCKED" and attempt < max_attempts:
                    _safe_stdout_line("[DAEMON_WARN] install hit file lock, retry once after short backoff")
                    time.sleep(1.2)
                    self._cleanup_torch_tilde_leftovers(pyexe)
                    attempt += 1
                    continue
                break
            with recent_lock:
                final_tail = "\n".join(recent_lines[-120:]) if recent_lines else ""
            if final_tail:
                self._task_merge_details(task_id, {"log_tail": final_tail})

            if not ok:
                primary = fail_primary or "dependency install failed"
                code = fail_code or "TASK_RUNTIME_ERROR"
                tail = fail_tail or []
                self._task_set_progress(task_id, 99, 100)
                raise RpcTaskError(
                    f"dependency install failed: {primary}",
                    error_code=code,
                    details={
                        "layers": chosen_layers,
                        "primary_error": primary,
                        "log_tail": "\n".join(tail[-40:]),
                        "attempts": attempt,
                    },
                )

            if force_verify:
                verify_fail: dict[str, str] = {}
                verify_fn = getattr(db, "_verify_layer_runtime", None)
                for lyr in chosen_layers:
                    if not callable(verify_fn):
                        break
                    try:
                        v_ok, v_err = verify_fn(str(pyexe), str(lyr), timeout=120, strict=True)
                    except Exception as e:
                        v_ok, v_err = False, str(e)
                    if bool(v_ok):
                        _safe_stdout_line(f"[DAEMON_VERIFY] {lyr} strict verify ok")
                    else:
                        verify_fail[str(lyr)] = str(v_err or "")[:1200]
                        _safe_stdout_line(f"[DAEMON_VERIFY] {lyr} strict verify failed: {v_err}")
                if verify_fail:
                    self._task_set_progress(task_id, 99, 100)
                    raise RpcTaskError(
                        "force verify failed after dependency install",
                        error_code="TASK_RUNTIME_ERROR",
                        details={"verify_fail": verify_fail, "layers": chosen_layers},
                    )

            if ("HEAVY_CPU" in chosen_layers) or ("HEAVY_GPU" in chosen_layers):
                self._verify_layers_runtime(str(pyexe), chosen_layers)

            self._task_set_progress(task_id, 100, 100)
            installed = self._merge_state_layers(deps_dir, chosen_layers)
            return {"layers": chosen_layers, "installed_layers": installed, "skipped": {}}
        finally:
            builtins.print = orig_print

    def _merge_state_layers(self, deps_dir: str, layers: list[str]) -> list[str]:
        current = self._read_state_layers(deps_dir)
        merged: list[str] = list(current)
        for x in layers:
            if x not in merged:
                merged.append(x)
        if "HEAVY_GPU" in layers and "HEAVY_CPU" in merged:
            merged.remove("HEAVY_CPU")
        if "HEAVY_CPU" in layers and "HEAVY_GPU" in merged:
            merged.remove("HEAVY_GPU")
        self._write_state_layers(deps_dir, merged)
        return merged

    def _task_worker_loop(self) -> None:
        _log_event("task_worker_started", pid=os.getpid())
        while not self._stop_event.is_set():
            try:
                task_id = self.task_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if task_id is None:
                break
            try:
                self._run_task(task_id)
            finally:
                try:
                    self.task_queue.task_done()
                except Exception:
                    pass
        _log_event("task_worker_stopped", pid=os.getpid())

    def _run_task(self, task_id: str) -> None:
        task = self._task_get(task_id)
        if not task:
            return
        kind = str(task.get("kind", "") or "")
        params = dict(task.get("params", {}) or {})
        self._task_update(
            task_id,
            status=TASK_STATUS_RUNNING,
            started_at=time.time(),
            error="",
            error_type="",
            output={},
        )
        _log_event("task_started", task_id=task_id, kind=kind)
        try:
            if kind == TASK_KIND_PREDICT_IMAGE:
                out = self._task_predict_image(task_id, params)
            elif kind == TASK_KIND_PREDICT_PDF:
                out = self._task_predict_pdf(task_id, params)
            elif kind == TASK_KIND_INSTALL_DEPS:
                out = self._task_install_deps(task_id, params)
            elif kind == TASK_KIND_SWITCH_CPU_GPU:
                out = self._task_switch_cpu_gpu(task_id, params)
            else:
                raise RuntimeError(f"unknown task kind: {kind}")
            self._task_update(task_id, status=TASK_STATUS_SUCCESS, ended_at=time.time(), output=out or {})
            _log_event("task_succeeded", task_id=task_id, kind=kind)
        except RpcTaskError as e:
            self._task_update(
                task_id,
                status=TASK_STATUS_ERROR,
                ended_at=time.time(),
                error=str(e),
                error_type=e.__class__.__name__,
                error_code=e.error_code,
                details=_json_safe(e.details),
            )
            _log_event(
                "task_failed",
                task_id=task_id,
                kind=kind,
                error=str(e),
                error_type=e.__class__.__name__,
                error_code=e.error_code,
                details=_json_safe(e.details),
            )
        except RuntimeError as e:
            msg = str(e or "")
            if msg == "已取消":
                self._task_update(
                    task_id,
                    status=TASK_STATUS_CANCELLED,
                    ended_at=time.time(),
                    error=msg,
                    error_type="CancelledError",
                    error_code="TASK_CANCELLED",
                    details={},
                )
                _log_event("task_cancelled", task_id=task_id, kind=kind)
            else:
                self._task_update(
                    task_id,
                    status=TASK_STATUS_ERROR,
                    ended_at=time.time(),
                    error=msg,
                    error_type=e.__class__.__name__,
                    error_code="TASK_RUNTIME_ERROR",
                    details={},
                )
                _log_event("task_failed", task_id=task_id, kind=kind, error=msg, error_type=e.__class__.__name__)
        except Exception as e:
            self._task_update(
                task_id,
                status=TASK_STATUS_ERROR,
                ended_at=time.time(),
                error=str(e),
                error_type=e.__class__.__name__,
                error_code="TASK_RUNTIME_ERROR",
                details={},
            )
            _log_event("task_failed", task_id=task_id, kind=kind, error=str(e), error_type=e.__class__.__name__)

    def _task_predict_image(self, task_id: str, params: dict[str, Any]) -> dict[str, Any]:
        image_path = str((params or {}).get("image_path", "") or "")
        image_b64 = str((params or {}).get("image_b64", "") or "")
        model_name = str((params or {}).get("model_name", "pix2text") or "pix2text")
        wrapper = self._ensure_wrapper()
        if self._task_should_cancel(task_id):
            raise RuntimeError("已取消")
        if image_path:
            if not os.path.exists(image_path):
                raise RuntimeError(f"image not found: {image_path}")
            with Image.open(image_path) as img:
                with self.wrapper_lock:
                    result = wrapper.predict(img, model_name=model_name)
        elif image_b64:
            if "," in image_b64 and image_b64.strip().startswith("data:"):
                image_b64 = image_b64.split(",", 1)[1]
            try:
                raw = base64.b64decode(image_b64, validate=False)
            except Exception as e:
                raise RuntimeError(f"image_b64 decode failed: {e}")
            if not raw:
                raise RuntimeError("image_b64 empty after decode")
            try:
                with Image.open(io.BytesIO(raw)) as img:
                    with self.wrapper_lock:
                        result = wrapper.predict(img, model_name=model_name)
            except Exception as e:
                raise RuntimeError(f"image_b64 load failed: {e}")
        else:
            raise RuntimeError("image_path/image_b64 missing")
        if self._task_should_cancel(task_id):
            raise RuntimeError("已取消")
        text = str(result or "")
        export_formats, export_errors = build_export_formats(text)
        return {
            "result": text,
            "model_name": model_name,
            "result_formats": export_formats,
            "result_format_errors": export_errors,
        }

    def _task_predict_pdf(self, task_id: str, params: dict[str, Any]) -> dict[str, Any]:
        pdf_path = str((params or {}).get("pdf_path", "") or "")
        max_pages = int((params or {}).get("max_pages", 0) or 0)
        model_name = str((params or {}).get("model_name", "pix2text") or "pix2text")
        output_format = str((params or {}).get("output_format", "markdown") or "markdown")
        dpi = int((params or {}).get("dpi", 200) or 200)
        wrapper = self._ensure_wrapper()
        if not pdf_path:
            raise RuntimeError("pdf_path missing")
        if not os.path.exists(pdf_path):
            raise RuntimeError(f"pdf not found: {pdf_path}")
        try:
            import fitz  # type: ignore
        except Exception as e:
            raise RuntimeError(f"缺少 PyMuPDF 依赖: {e}")
        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            raise RuntimeError(f"PDF 打开失败: {e}")

        try:
            doc_pages = int(doc.page_count or 1)
            total = doc_pages if max_pages <= 0 else min(max(max_pages, 1), doc_pages)
            self._task_set_progress(task_id, 0, total)
            results = []
            for i in range(total):
                if self._task_should_cancel(task_id):
                    raise RuntimeError("已取消")
                page = doc.load_page(i)
                pix = page.get_pixmap(dpi=dpi, alpha=False)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                with self.wrapper_lock:
                    res = wrapper.predict(img, model_name=model_name)
                if self._task_should_cancel(task_id):
                    raise RuntimeError("已取消")
                results.append((res or "").strip())
                self._task_set_progress(task_id, i + 1, total)
            sep = "\n\n---\n\n" if output_format == "markdown" else "\n\n% --- Page ---\n\n"
            content = sep.join([r for r in results if r])
            if not content.strip():
                raise RuntimeError("识别结果为空")
            content_formats: dict[str, str] = {}
            content_format_errors: dict[str, str] = {}
            if output_format == "markdown":
                content_formats["markdown"] = content.strip()
                content_formats["latex"] = _to_latex_from_markdown(content)
            else:
                content_formats["latex"] = content.strip()
                content_formats["markdown"] = _to_markdown_from_latex(content)
            if _looks_like_single_formula(content):
                try:
                    extra_formats, extra_errors = build_export_formats(content)
                    for key in ("mathml", "mathml_mml", "mathml_m", "mathml_attr", "omml"):
                        if extra_formats.get(key):
                            content_formats[key] = str(extra_formats.get(key) or "")
                        if extra_errors.get(key):
                            content_format_errors[key] = str(extra_errors.get(key) or "")
                except Exception as exc:
                    content_format_errors["omml"] = str(exc)
            return {
                "content": content.strip(),
                "pages": total,
                "output_format": output_format,
                "model_name": model_name,
                "content_formats": content_formats,
                "content_format_errors": content_format_errors,
            }
        finally:
            try:
                doc.close()
            except Exception:
                pass

    def _task_install_deps(self, task_id: str, params: dict[str, Any]) -> dict[str, Any]:
        layers = self._normalize_layers((params or {}).get("layers", []))
        deps_dir = str((params or {}).get("deps_dir", "") or "").strip()
        mirror = str((params or {}).get("mirror", "") or "").strip().lower()
        force_verify = bool((params or {}).get("force_verify", False))
        pyexe, resolved_deps_dir = self._resolve_python_for_deps(deps_dir)
        try:
            result = self._install_layers_via_deps_bootstrap(
                task_id,
                layers=layers,
                pyexe=pyexe,
                deps_dir=resolved_deps_dir,
                mirror=mirror,
                force_verify=force_verify,
            )
            merged_layers = self._merge_state_layers(
                resolved_deps_dir, list(result.get("layers", []))
            )
        except RuntimeError as e:
            if str(e or "") == "已取消":
                raise
            raise
        except RpcTaskError:
            raise
        except Exception as e:
            _safe_stdout_line(f"[DAEMON_WARN] deps_bootstrap path failed, fallback installer: {e}")
            result = self._install_layers(
                task_id,
                layers=layers,
                pyexe=pyexe,
                mirror=mirror,
                force_verify=force_verify,
            )
            merged_layers = self._merge_state_layers(resolved_deps_dir, list(result.get("layers", [])))
        return {
            "message": "dependencies installed",
            "deps_dir": resolved_deps_dir,
            "layers": list(result.get("layers", [])),
            "skipped": result.get("skipped", {}),
            "installed_layers": merged_layers,
            "python": pyexe,
            "mirror": "tuna" if self._use_mirror(mirror) else "official",
        }

    def _task_switch_cpu_gpu(self, task_id: str, params: dict[str, Any]) -> dict[str, Any]:
        target = str((params or {}).get("target", "") or "").strip().lower()
        cuda_tag = str((params or {}).get("cuda_tag", "") or "").strip().lower()
        deps_dir = str((params or {}).get("deps_dir", "") or "").strip()
        if target not in ("cpu", "gpu"):
            raise RpcTaskError(
                "target must be 'cpu' or 'gpu'",
                error_code="RPC_INVALID_PARAMS",
                details={"target": target},
            )

        layers = ["HEAVY_GPU"] if target == "gpu" else ["HEAVY_CPU"]
        pyexe, resolved_deps_dir = self._resolve_python_for_deps(deps_dir)
        mirror = str((params or {}).get("mirror", "") or "").strip().lower()
        try:
            result = self._install_layers_via_deps_bootstrap(
                task_id,
                layers=layers,
                pyexe=pyexe,
                deps_dir=resolved_deps_dir,
                mirror=mirror,
                force_verify=True,
            )
            merged_layers = self._merge_state_layers(
                resolved_deps_dir, list(result.get("layers", []))
            )
        except RuntimeError as e:
            if str(e or "") == "已取消":
                raise
            raise
        except RpcTaskError:
            raise
        except Exception as e:
            _safe_stdout_line(f"[DAEMON_WARN] deps_bootstrap switch path failed, fallback installer: {e}")
            result = self._install_layers(
                task_id,
                layers=layers,
                pyexe=pyexe,
                mirror=mirror,
                force_verify=True,
                cuda_tag=cuda_tag,
            )
            merged_layers = self._merge_state_layers(resolved_deps_dir, list(result.get("layers", [])))
        return {
            "message": f"switched to {target}",
            "target": target,
            "cuda_tag": str(result.get("cuda_tag", "") or ""),
            "deps_dir": resolved_deps_dir,
            "layers": list(result.get("layers", [])),
            "installed_layers": merged_layers,
            "python": pyexe,
        }

    def stop(self) -> None:
        self._stop_event.set()
        try:
            with self.wrapper_lock:
                wrapper = self.wrapper
            if wrapper is not None:
                try:
                    wrapper._stop_pix2text_worker()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            self.task_queue.put_nowait(None)
        except Exception:
            pass
        try:
            if self.task_worker.is_alive():
                self.task_worker.join(timeout=2.0)
        except Exception:
            pass

    def dispatch(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        _log_event("request_begin", method=method)
        if method == METHOD_HEALTH:
            with self.wrapper_lock:
                wrapper = self.wrapper
                ready = bool(wrapper.is_ready()) if wrapper is not None else False
                status = str(wrapper.get_status_text()) if wrapper is not None else "model not initialized"
                resp = {
                    "ok": True,
                    "pid": os.getpid(),
                    "ready": ready,
                    "status": status,
                    "model": "pix2text",
                    "contract": {
                        "name": CONTRACT_NAME,
                        "version": CONTRACT_VERSION,
                    },
                }
            _log_event("request_end", method=method, ok=True, ready=resp.get("ready"))
            return resp
        if method == METHOD_WARMUP:
            wrapper = self._ensure_wrapper()
            with self.wrapper_lock:
                ok = bool(wrapper._lazy_load_pix2text())
                ready = bool(wrapper.is_ready())
            resp = {"ok": ok, "ready": ready}
            _log_event("request_end", method=method, ok=ok, ready=ready)
            return resp
        if method == METHOD_MODEL_STATUS:
            with self.wrapper_lock:
                wrapper = self.wrapper
                resp = {
                    "ok": True,
                    "ready": bool(wrapper.is_ready()) if wrapper is not None else False,
                    "status": str(wrapper.get_status_text()) if wrapper is not None else "model not initialized",
                    "last_used_model": getattr(wrapper, "last_used_model", None) if wrapper is not None else None,
            }
            _log_event("request_end", method=method, ok=True, ready=resp.get("ready"))
            return resp
        if method == METHOD_PREDICT_IMAGE:
            resp = _error_response(
                "method 'predict_image' is deprecated; use task_submit(kind='predict_image') + task_status",
                error_type="NotImplementedError",
                error_code="RPC_DEPRECATED_METHOD",
                details={"replacement": "task_submit + task_status", "removal_target": "2.0.0"},
            )
            _log_event("request_end", method=method, ok=False, error_code="RPC_DEPRECATED_METHOD")
            return resp
        if method == METHOD_TASK_SUBMIT:
            kind = str((params or {}).get("kind", "") or "")
            task_params = (params or {}).get("params", {})
            if not isinstance(task_params, dict):
                task_params = {}
            local_supported = {
                TASK_KIND_PREDICT_IMAGE,
                TASK_KIND_PREDICT_PDF,
                TASK_KIND_INSTALL_DEPS,
                TASK_KIND_SWITCH_CPU_GPU,
            }
            if (kind not in local_supported) and (not is_supported_task_kind(kind)):
                resp = _error_response(
                    f"unsupported task kind: {kind}",
                    error_type="ValueError",
                    error_code="TASK_KIND_UNSUPPORTED",
                    details={"kind": kind},
                )
                _log_event("request_end", method=method, ok=False, error=resp.get("error"))
                return resp
            task_id = self._task_create(kind, task_params)
            resp = {"ok": True, "task_id": task_id}
            _log_event("request_end", method=method, ok=True, task_id=task_id, kind=kind)
            return resp
        if method == METHOD_TASK_STATUS:
            task_id = str((params or {}).get("task_id", "") or "")
            if not task_id:
                resp = _error_response("task_id missing", error_type="ValueError", error_code="RPC_INVALID_PARAMS")
                _log_event("request_end", method=method, ok=False, error=resp.get("error"))
                return resp
            task = self._task_get(task_id)
            if not task:
                resp = _error_response(
                    f"task not found: {task_id}",
                    error_type="FileNotFoundError",
                    error_code="TASK_NOT_FOUND",
                    details={"task_id": task_id},
                )
                _log_event("request_end", method=method, ok=False, error=resp.get("error"))
                return resp
            resp = {"ok": True, "task": self._task_snapshot(task)}
            _log_event("request_end", method=method, ok=True, task_id=task_id, status=task.get("status", ""))
            return resp
        if method == METHOD_TASK_CANCEL:
            task_id = str((params or {}).get("task_id", "") or "")
            if not task_id:
                resp = _error_response("task_id missing", error_type="ValueError", error_code="RPC_INVALID_PARAMS")
                _log_event("request_end", method=method, ok=False, error=resp.get("error"))
                return resp
            task = self._task_update(task_id, cancel_requested=True)
            if not task:
                resp = _error_response(
                    f"task not found: {task_id}",
                    error_type="FileNotFoundError",
                    error_code="TASK_NOT_FOUND",
                    details={"task_id": task_id},
                )
                _log_event("request_end", method=method, ok=False, error=resp.get("error"))
                return resp
            resp = {"ok": True, "task_id": task_id}
            _log_event("request_end", method=method, ok=True, task_id=task_id, cancel_requested=True)
            return resp
        if method == METHOD_SHUTDOWN:
            try:
                self.stop()
                if self.server_ref is not None:
                    threading.Thread(target=self.server_ref.shutdown, daemon=True).start()
            except Exception:
                pass
            _log_event("shutdown_requested")
            return {"ok": True}
        hint = "known method but unsupported in server implementation" if is_known_method(method) else ""
        if not hint and METHODS:
            hint = f"known={','.join(METHODS)}"
        resp = {
            "ok": False,
            "error": f"unknown method: {method}{f' ({hint})' if hint else ''}",
            "error_type": "NotImplementedError",
            "error_code": "RPC_UNKNOWN_METHOD",
        }
        _log_event("request_end", method=method, ok=False, error=resp.get("error"))
        return resp


class _RequestHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        state: _State = self.server.state  # type: ignore[attr-defined]
        raw = self.rfile.readline()
        if not raw:
            return
        try:
            req = json.loads(raw.decode("utf-8", errors="replace").strip() or "{}")
            if not isinstance(req, dict):
                raise ValueError("request must be object")
        except Exception as e:
            _log_event("bad_request", error=str(e), client=str(getattr(self, "client_address", "")))
            self.wfile.write((json.dumps(_error_response(f"bad request: {e}", error_type=e.__class__.__name__, error_code="RPC_BAD_REQUEST")) + "\n").encode("utf-8"))
            return

        token = str(req.get("token", "") or "")
        if state.token and token != state.token:
            _log_event("unauthorized", client=str(getattr(self, "client_address", "")))
            self.wfile.write((json.dumps(_error_response("unauthorized", error_type="PermissionError", error_code="RPC_UNAUTHORIZED")) + "\n").encode("utf-8"))
            return

        method = str(req.get("method", "") or "")
        params = req.get("params", {})
        if not isinstance(params, dict):
            params = {}
        try:
            resp = state.dispatch(method, params)
        except Exception as e:
            include_trace = str(os.environ.get("LATEXSNIPPER_DAEMON_TRACE", "") or "").strip().lower() in (
                "1",
                "true",
                "yes",
                "on",
            )
            _log_event("request_exception", method=method, error=str(e), error_type=e.__class__.__name__)
            resp = _error_payload(e, include_trace=include_trace)
        self.wfile.write((json.dumps(resp, ensure_ascii=False) + "\n").encode("utf-8", errors="replace"))


class _ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> int:
    parser = argparse.ArgumentParser("latexsnipper-daemon")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--token", default="")
    parser.add_argument("--model", default="pix2text")
    args = parser.parse_args()

    _log_event("daemon_start", host=args.host, port=args.port, model=args.model, pid=os.getpid())
    state = _State(model_name=args.model, token=args.token)
    with _ThreadingTCPServer((args.host, int(args.port)), _RequestHandler) as srv:
        state.server_ref = srv
        srv.state = state  # type: ignore[attr-defined]
        _safe_stdout_line(f"[daemon] ready host={args.host} port={args.port} pid={os.getpid()}")
        srv.serve_forever(poll_interval=0.2)
    try:
        state.stop()
    except Exception:
        pass
    _log_event("daemon_exit", pid=os.getpid())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
