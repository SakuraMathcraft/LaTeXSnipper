# coding: utf-8

from __future__ import annotations

from collections import deque
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
from typing import Any

from PIL import Image

try:
    from PyQt6.QtCore import QObject, pyqtSignal
except Exception:

    class _Signal:
        def __init__(self):
            self._handlers = []

        def connect(self, fn):
            if callable(fn) and fn not in self._handlers:
                self._handlers.append(fn)

        def emit(self, *args, **kwargs):
            for fn in list(self._handlers):
                try:
                    fn(*args, **kwargs)
                except Exception:
                    pass

    class _SignalDescriptor:
        def __set_name__(self, _owner, name):
            self._name = f"__sig_{name}"

        def __get__(self, instance, _owner):
            if instance is None:
                return self
            sig = instance.__dict__.get(self._name)
            if sig is None:
                sig = _Signal()
                instance.__dict__[self._name] = sig
            return sig

    def pyqtSignal(*_args, **_kwargs):
        return _SignalDescriptor()

    class QObject:
        def __init__(self, *args, **kwargs):
            super().__init__()


os.environ.setdefault("ORT_DISABLE_AZURE", "1")


MODEL_MODES = {
    "mathcraft": "formula",
    "mathcraft_formula": "formula",
    "mathcraft_text": "text",
    "mathcraft_mixed": "mixed",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _worker_code_roots() -> list[Path]:
    candidates: list[Path] = []

    def add(path: str | Path | None) -> None:
        if not path:
            return
        try:
            p = Path(path).resolve()
        except Exception:
            return
        if p not in candidates:
            candidates.append(p)

    add(_repo_root())
    add(_repo_root() / "_internal")
    try:
        add(getattr(sys, "_MEIPASS", None))
    except Exception:
        pass
    try:
        exe_dir = Path(sys.executable).resolve().parent
        add(exe_dir)
        add(exe_dir / "_internal")
    except Exception:
        pass
    try:
        current = Path(__file__).resolve()
        for parent in current.parents:
            if (parent / "mathcraft_ocr").is_dir() or (parent / "_internal" / "mathcraft_ocr").is_dir():
                add(parent)
                add(parent / "_internal")
    except Exception:
        pass
    return [root for root in candidates if root.is_dir()]


def _worker_pythonpath() -> str:
    return os.pathsep.join(str(root) for root in _worker_code_roots())


def _failed_warmup_component_details(result: dict[str, Any]) -> list[str]:
    statuses = result.get("component_statuses", [])
    if not isinstance(statuses, list):
        return []
    details: list[str] = []
    for status in statuses:
        if not isinstance(status, dict) or bool(status.get("ready")):
            continue
        model_id = str(status.get("model_id") or "").strip()
        detail = str(status.get("detail") or "").strip()
        if model_id and detail:
            details.append(f"{model_id}: {detail}")
        elif detail:
            details.append(detail)
        elif model_id:
            details.append(f"{model_id}: not ready")
    return details


def _bundled_mathcraft_models_dir() -> Path | None:
    candidates: list[Path] = []
    try:
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "MathCraft" / "models")
    except Exception:
        pass
    try:
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "_internal" / "MathCraft" / "models")
        candidates.append(exe_dir / "MathCraft" / "models")
    except Exception:
        pass
    try:
        for root in _worker_code_roots():
            candidates.append(root / "MathCraft" / "models")
    except Exception:
        pass
    for candidate in candidates:
        try:
            if candidate.is_dir():
                return candidate.resolve()
        except Exception:
            continue
    return None


def _subprocess_creationflags() -> int:
    if os.name != "nt":
        return 0
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _same_path(left: str | Path | None, right: str | Path | None) -> bool:
    if not left or not right:
        return False
    try:
        return os.path.normcase(os.path.abspath(str(left))) == os.path.normcase(os.path.abspath(str(right)))
    except Exception:
        return str(left) == str(right)


def _find_install_base_python(base_dir: str | Path | None) -> Path | None:
    if not base_dir:
        return None
    base = Path(base_dir)
    candidates = [
        base / "python.exe",
        base / "Scripts" / "python.exe",
        base / "python311" / "python.exe",
        base / "python311" / "Scripts" / "python.exe",
        base / "Python311" / "python.exe",
        base / "Python311" / "Scripts" / "python.exe",
        base / "venv" / "Scripts" / "python.exe",
        base / ".venv" / "Scripts" / "python.exe",
        base / "python_full" / "python.exe",
    ]
    try:
        for child in sorted(base.glob("python*")):
            if child.is_dir():
                candidates.append(child / "python.exe")
                candidates.append(child / "Scripts" / "python.exe")
    except Exception:
        pass
    for candidate in candidates:
        try:
            if candidate.exists() and candidate.is_file():
                return candidate
        except Exception:
            continue
    return None


def _configured_install_base_python() -> Path | None:
    raw_values: list[str] = []
    for key in ("LATEXSNIPPER_DEPS_DIR", "LATEXSNIPPER_INSTALL_BASE_DIR"):
        raw = (os.environ.get(key, "") or "").strip()
        if raw:
            raw_values.append(raw)
    try:
        cfg = Path.home() / ".latexsnipper" / "LaTeXSnipper_config.json"
        if cfg.exists():
            data = json.loads(cfg.read_text(encoding="utf-8"))
            raw = str(data.get("install_base_dir", "") or "").strip() if isinstance(data, dict) else ""
            if raw:
                raw_values.append(raw)
    except Exception:
        pass
    seen: set[str] = set()
    for raw in raw_values:
        try:
            key = os.path.normcase(os.path.abspath(raw))
        except Exception:
            key = raw
        if key in seen:
            continue
        seen.add(key)
        pyexe = _find_install_base_python(raw)
        if pyexe is not None:
            return pyexe
    return None


def _looks_like_packaged_template_python(pyexe: str | Path | None) -> bool:
    if not pyexe:
        return False
    try:
        normalized = os.path.normcase(os.path.abspath(str(pyexe)))
    except Exception:
        normalized = str(pyexe).lower()
    return f"{os.sep}_internal{os.sep}deps{os.sep}" in normalized and normalized.endswith("python.exe")


def get_deps_python() -> str:
    pyexe = os.environ.get("LATEXSNIPPER_PYEXE", "")
    configured_py = _configured_install_base_python()
    if configured_py is not None and pyexe and os.path.exists(pyexe):
        if _looks_like_packaged_template_python(pyexe) and not _same_path(pyexe, configured_py):
            return str(configured_py)
    if pyexe and os.path.exists(pyexe):
        return pyexe
    if configured_py is not None:
        return str(configured_py)
    if getattr(sys, "frozen", False):
        print("[WARN] packaged mode: deps python not configured, fallback to current runtime")
    return sys.executable


def _infer_provider_preference_from_deps_state(pyexe: str) -> str:
    candidates: list[Path] = []
    try:
        py_path = Path(pyexe).resolve()
        candidates.append(py_path.parent.parent / ".deps_state.json")
        candidates.append(py_path.parent / ".deps_state.json")
    except Exception:
        pass
    for raw in (os.environ.get("LATEXSNIPPER_DEPS_DIR", ""),):
        if raw:
            try:
                candidates.append(Path(raw).resolve() / ".deps_state.json")
            except Exception:
                pass

    for state_path in candidates:
        try:
            if not state_path.is_file():
                continue
            data = json.loads(state_path.read_text(encoding="utf-8-sig"))
            layers = {str(item) for item in data.get("installed_layers", [])}
            if "MATHCRAFT_GPU" in layers:
                return "gpu"
            if "MATHCRAFT_CPU" in layers:
                return "cpu"
        except Exception:
            continue
    return "auto"


def resolve_mathcraft_provider_preference() -> str:
    explicit = (os.environ.get("MATHCRAFT_PROVIDER", "") or "").strip().lower()
    if explicit in {"auto", "cpu", "gpu"}:
        return explicit
    return _infer_provider_preference_from_deps_state(get_deps_python())


def classify_mathcraft_failure(detail: str) -> dict[str, str]:
    raw = str(detail or "").strip()
    lower = raw.lower()

    def _pack(code: str, title: str, user_message: str, log_message: str) -> dict[str, str]:
        return {
            "code": code,
            "title": title,
            "user_message": user_message,
            "log_message": log_message,
        }

    def _looks_like_cuda_runtime_error() -> bool:
        try:
            from mathcraft_ocr.error_patterns import looks_like_cuda_runtime_error
        except Exception:
            return False
        return looks_like_cuda_runtime_error(raw)

    def _looks_like_onnxruntime_install_error() -> bool:
        try:
            from mathcraft_ocr.error_patterns import looks_like_onnxruntime_install_error
        except Exception:
            markers = (
                "failed to import onnxruntime",
                "failed to query onnx providers",
                "onnxruntime missing get_available_providers",
                "missing get_available_providers",
                "module 'onnxruntime' has no attribute 'get_available_providers'",
                "onnxruntime dependency is incomplete",
            )
            return any(marker in lower for marker in markers)
        return looks_like_onnxruntime_install_error(raw)

    if not raw:
        return _pack(
            "UNKNOWN",
            "模型预热未完成",
            "MathCraft OCR 预热失败，请打开运行日志查看具体原因。",
            "未拿到明确异常文本，需要结合运行日志继续排查。",
        )
    if "no module named" in lower and "mathcraft_ocr" in lower:
        return _pack(
            "MATHCRAFT_MISSING",
            "缺少 MathCraft OCR",
            "未找到 MathCraft OCR 包，请检查程序文件是否完整。",
            "mathcraft_ocr 模块不可导入，当前内置识别链路不可用。",
        )
    if "no module named" in lower and "onnxruntime" in lower:
        return _pack(
            "ONNXRUNTIME_MISSING",
            "缺少 onnxruntime",
            "未安装 onnxruntime 依赖，请重新校验依赖层是否安装完整。",
            "onnxruntime 模块缺失，MathCraft ONNX 后端不可用。",
        )
    if _looks_like_onnxruntime_install_error():
        return _pack(
            "ONNXRUNTIME_BROKEN",
            "onnxruntime 依赖异常",
            "onnxruntime 依赖未正确安装或被残留包污染，请通过依赖向导重装 MATHCRAFT_CPU 或 MATHCRAFT_GPU 后端。",
            f"onnxruntime 可导入但运行时接口不完整或 provider 查询失败: {raw[:300]}",
        )
    mathcraft_runtime_modules = (
        "rapidocr",
        "cv2",
        "opencv",
        "numpy",
        "pil",
        "pillow",
        "transformers",
        "tokenizers",
    )
    if "no module named" in lower and any(module in lower for module in mathcraft_runtime_modules):
        return _pack(
            "MATHCRAFT_DEP_MISSING",
            "MathCraft 依赖不完整",
            "当前依赖环境缺少 MathCraft OCR 运行依赖，请通过依赖向导安装 BASIC、CORE 和对应的 MATHCRAFT_CPU/GPU 层。",
            f"MathCraft worker 缺少运行依赖，通常是打包模板 Python 尚未部署完整依赖: {raw[:300]}",
        )
    if "not ready" in lower and "missing" in lower and "missing=[]" not in lower:
        return _pack(
            "MODEL_CACHE_INCOMPLETE",
            "模型缓存不完整",
            "MathCraft OCR 模型缓存不完整，请补齐模型权重后重试。",
            f"MathCraft 模型缓存不完整: {raw[:300]}",
        )
    if "failed to download model" in lower or "no usable download source" in lower:
        return _pack(
            "MODEL_DOWNLOAD_FAILED",
            "模型权重下载失败",
            "MathCraft OCR 模型权重下载失败，请检查网络连接或稍后重试。",
            f"MathCraft 模型权重下载失败: {raw[:300]}",
        )
    if "list index out of range" in lower or ("indexerror" in lower and "rapidocr" in lower):
        return _pack(
            "OCR_VOCAB_MISMATCH",
            "OCR 字典与模型不匹配",
            "MathCraft 文字识别模型与字典不匹配，请更新或重新下载 MathCraft 模型权重。",
            f"RapidOCR 解码越界，通常是 PP-OCR 识别模型与字典文件不匹配: {raw[:300]}",
        )
    if _looks_like_cuda_runtime_error():
        return _pack(
            "CUDA_RUNTIME_BROKEN",
            "CUDA 环境异常",
            "检测到 CUDA 环境异常，当前 GPU 推理不可用，请修复 CUDA 环境或改用 CPU。",
            "CUDAExecutionProvider 初始化失败，常见原因是 CUDA/cuDNN 版本不匹配或 PATH 配置错误。",
        )
    if "unsupported worker action" in lower or "unsupported warmup profile" in lower:
        return _pack(
            "UNSUPPORTED_MODE",
            "识别模式不支持",
            "当前 MathCraft OCR 版本不支持该识别模式。",
            f"请求了 MathCraft v1 未支持的模式: {raw[:300]}",
        )
    if "timeout" in lower:
        return _pack(
            "WORKER_TIMEOUT",
            "识别进程超时",
            "MathCraft OCR 运行进程响应超时，请稍后重试或检查模型运行环境。",
            "MathCraft OCR 运行进程超时，需要检查模型初始化耗时、图片大小和运行环境。",
        )
    return _pack(
        "UNKNOWN",
        "模型运行异常",
        "MathCraft OCR 运行异常，请打开运行日志查看具体原因。",
        f"未命中已知错误分类，原始错误: {raw[:300]}",
    )


class ModelWrapper(QObject):
    """MathCraft-only internal OCR wrapper."""

    status_signal = pyqtSignal(str)

    def __init__(self, default_model: str | None = None, auto_warmup: bool = True):
        super().__init__()
        self.device = "cpu"
        self.last_used_model = None
        self._default_model = self._normalize_model_name(default_model or "mathcraft")
        self._worker: subprocess.Popen | None = None
        self._worker_lock = threading.Lock()
        self._request_lock = threading.Lock()
        self._request_seq = 0
        self._ready = False
        self._import_failed = False
        self._last_error = ""
        self._last_error_code = ""
        self._provider = resolve_mathcraft_provider_preference()
        self._ready_modes: set[str] = set()
        self._stderr_lock = threading.Lock()
        self._worker_stderr_tail: deque[str] = deque(maxlen=80)
        self._cache_events_seen: set[str] = set()

        self._emit(f"[INFO] MathCraft OCR 后端偏好: {self._provider}")
        self._emit(f"[INFO] MathCraft OCR 依赖解释器: {get_deps_python()}")
        if auto_warmup:
            self._lazy_load_mathcraft()

    def _emit(self, msg: str) -> None:
        try:
            print(msg, flush=True)
        except Exception:
            pass
        try:
            self.status_signal.emit(msg)
        except Exception:
            pass

    def _build_subprocess_env(self) -> dict:
        env = os.environ.copy()
        for key in ("PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP", "PYTHONEXECUTABLE", "MATHCRAFT_HOME"):
            env.pop(key, None)
        env["PYTHONNOUSERSITE"] = "1"
        env["PYTHONPATH"] = _worker_pythonpath()
        env["ORT_DISABLE_AZURE"] = "1"
        bundled_models = _bundled_mathcraft_models_dir()
        if bundled_models is not None:
            env["MATHCRAFT_BUNDLED_MODELS_DIR"] = str(bundled_models)
        else:
            env.pop("MATHCRAFT_BUNDLED_MODELS_DIR", None)
        return env

    def _normalize_model_name(self, model_name: str | None) -> str:
        model = str(model_name or "mathcraft").strip().lower()
        if model in MODEL_MODES:
            return model
        return "mathcraft"

    def _mode_for_model(self, model_name: str | None) -> str:
        model = self._normalize_model_name(model_name)
        return MODEL_MODES.get(model, "formula")

    def set_default_model(self, model_name: str | None) -> None:
        self._default_model = self._normalize_model_name(model_name or "mathcraft")

    def _next_request_id(self) -> str:
        self._request_seq += 1
        return f"mathcraft-{self._request_seq}"

    def _worker_argv(self) -> list[str]:
        roots = [str(root) for root in _worker_code_roots()]
        code = (
            "import sys; "
            f"[sys.path.insert(0, p) for p in reversed({roots!r}) if p not in sys.path]; "
            "from mathcraft_ocr.cli import main; "
            f"raise SystemExit(main(['worker', '--provider', {self._provider!r}]))"
        )
        return [get_deps_python(), "-u", "-c", code]

    def _remember_worker_stderr(self, text: str) -> None:
        if not text:
            return
        with self._stderr_lock:
            self._worker_stderr_tail.append(text)

    def _worker_stderr_text(self, limit: int = 4000) -> str:
        with self._stderr_lock:
            text = "\n".join(self._worker_stderr_tail)
        return text.strip()[-limit:]

    def _emit_cache_event_once(self, event: str) -> None:
        event = str(event or "").strip()
        if not event or event in self._cache_events_seen:
            return
        self._cache_events_seen.add(event)
        self._emit(f"[INFO] MathCraft model cache: {event}")

    def _start_worker_stderr_pump(self, proc: subprocess.Popen) -> None:
        stderr = proc.stderr
        if stderr is None:
            return

        def _pump() -> None:
            try:
                for raw_line in stderr:
                    line = str(raw_line or "").strip()
                    if not line:
                        continue
                    self._remember_worker_stderr(line)
                    prefix = "[MATHCRAFT_CACHE]"
                    if line.startswith(prefix):
                        self._emit_cache_event_once(line[len(prefix):].strip())
            except Exception:
                return

        threading.Thread(target=_pump, daemon=True).start()

    def _ensure_worker(self) -> bool:
        proc = self._worker
        if proc is not None and proc.poll() is None:
            return True
        with self._worker_lock:
            proc = self._worker
            if proc is not None and proc.poll() is None:
                return True
            try:
                self._cache_events_seen.clear()
                with self._stderr_lock:
                    self._worker_stderr_tail.clear()
                proc = subprocess.Popen(
                    self._worker_argv(),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=self._build_subprocess_env(),
                    creationflags=_subprocess_creationflags(),
                )
                self._worker = proc
                self._start_worker_stderr_pump(proc)
                return True
            except Exception as exc:
                self._set_error(str(exc))
                self._emit(f"[ERROR] MathCraft OCR 运行进程启动失败: {exc}")
                self._worker = None
                return False

    def _send_worker_request(self, payload: dict[str, Any], timeout_sec: float | None = 300.0) -> dict[str, Any]:
        if not self._ensure_worker():
            raise RuntimeError(self._last_error or "MathCraft OCR 运行进程启动失败")
        proc = self._worker
        if proc is None or proc.stdin is None or proc.stdout is None:
            raise RuntimeError("MathCraft OCR 运行进程管道不可用")

        request = dict(payload)
        request["id"] = request.get("id") or self._next_request_id()
        with self._request_lock:
            try:
                proc.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
                proc.stdin.flush()
            except Exception as exc:
                self._stop_mathcraft_worker()
                raise RuntimeError(f"MathCraft OCR 请求发送失败: {exc}") from exc
            lines: queue.Queue[str | BaseException] = queue.Queue(maxsize=1)

            def _readline() -> None:
                try:
                    lines.put(proc.stdout.readline())
                except BaseException as exc:
                    lines.put(exc)

            reader = threading.Thread(target=_readline, daemon=True)
            reader.start()
            try:
                line_or_exc = (
                    lines.get()
                    if timeout_sec is None
                    else lines.get(timeout=max(float(timeout_sec), 1.0))
                )
            except queue.Empty as exc:
                self._stop_mathcraft_worker()
                raise RuntimeError(f"MathCraft OCR 运行进程超时（>{timeout_sec:.0f}s）") from exc
            if isinstance(line_or_exc, BaseException):
                self._stop_mathcraft_worker()
                raise RuntimeError(f"MathCraft OCR 响应读取失败: {line_or_exc}") from line_or_exc
            line = line_or_exc

        if not line:
            detail = self._worker_stderr_text()
            self._stop_mathcraft_worker()
            if detail:
                raise RuntimeError(f"MathCraft OCR 运行进程已退出且没有返回结果: {detail}")
            raise RuntimeError("MathCraft OCR 运行进程已退出且没有返回结果")
        try:
            response = json.loads(line)
        except Exception as exc:
            raise RuntimeError(f"MathCraft OCR 返回了无效 JSON: {line[:300]}") from exc
        if not response.get("ok"):
            err = response.get("error", {})
            message = err.get("message") if isinstance(err, dict) else str(err)
            raise RuntimeError(str(message or "MathCraft OCR 运行错误"))
        result = response.get("result")
        return result if isinstance(result, dict) else {}

    def _set_error(self, detail: str) -> dict[str, str]:
        info = classify_mathcraft_failure(detail)
        self._last_error = str(info.get("user_message", "") or detail or "").strip()
        self._last_error_code = str(info.get("code", "") or "").strip()
        self._import_failed = True
        self._ready = False
        return info

    def _clear_error(self) -> None:
        self._last_error = ""
        self._last_error_code = ""
        self._import_failed = False

    def _stop_mathcraft_worker(self) -> None:
        proc = self._worker
        self._worker = None
        if not proc:
            self._ready = False
            return
        try:
            if proc.stdin and proc.poll() is None:
                proc.stdin.write(json.dumps({"id": self._next_request_id(), "action": "shutdown"}) + "\n")
                proc.stdin.flush()
        except Exception:
            pass
        try:
            proc.terminate()
        except Exception:
            pass
        self._ready = False
        self._ready_modes.clear()

    def _lazy_load_mathcraft(self, model_name: str | None = None) -> bool:
        model = self._normalize_model_name(model_name or self._default_model)
        mode = self._mode_for_model(model)
        self._default_model = model
        if mode in self._ready_modes:
            self._ready = True
            return True
        try:
            result = self._send_worker_request(
                {
                    "action": "warmup",
                    "profile": mode,
                },
                timeout_sec=None,
            )
            ready = bool(result.get("ready"))
            if not ready:
                missing = result.get("missing_models", [])
                unsupported = result.get("unsupported_models", [])
                failed_components = _failed_warmup_component_details(result)
                detail = (
                    f"MathCraft runtime is not ready: missing={missing}, "
                    f"unsupported={unsupported}"
                )
                if failed_components:
                    detail = f"{detail}, failed_components={failed_components}"
                raise RuntimeError(detail)
            provider = result.get("provider_info", {})
            if isinstance(provider, dict):
                self.device = str(provider.get("device") or self.device or "cpu")
                active_provider = str(provider.get("active_provider") or "")
            else:
                active_provider = ""
            cache_events = result.get("cache_events", [])
            if isinstance(cache_events, list):
                for event in cache_events:
                    if event:
                        self._emit_cache_event_once(str(event))
            self._ready = True
            self._ready_modes.add(mode)
            self._clear_error()
            self._emit(
                "[INFO] MathCraft OCR 已就绪"
                f"{f'（实际后端: {active_provider}）' if active_provider else ''}"
            )
            return True
        except Exception as exc:
            info = self._set_error(str(exc))
            self._emit(f"[WARN] MathCraft OCR warmup failed [{info['code']}]: {exc}")
            self._emit(f"[DIAG] {info['log_message']}")
            return False

    def is_ready(self) -> bool:
        return self._ready

    def is_model_ready(self, model_name: str) -> bool:
        try:
            mode = self._mode_for_model(model_name)
        except Exception:
            return False
        return mode in self._ready_modes

    def get_error(self) -> str | None:
        return self._last_error if self._import_failed else None

    def get_status_text(self) -> str:
        if self._import_failed:
            return f"model load failed: {self._last_error or 'MathCraft OCR not ready'}"
        if self._ready:
            return f"model ready (MathCraft, device={self.device})"
        return "model not loaded"

    def predict_result(self, pil_img: Image.Image, model_name: str = "mathcraft") -> dict[str, Any]:
        model = self._normalize_model_name(model_name)
        mode = self._mode_for_model(model)
        if mode not in self._ready_modes and not self._lazy_load_mathcraft(model):
            raise RuntimeError(self._last_error or "MathCraft OCR not ready")

        tmp_path = ""
        try:
            image_rgb = pil_img.convert("RGB")
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = tmp.name
                image_rgb.save(tmp, format="PNG")
            if mode == "formula":
                result = self._send_worker_request(
                    {"action": "recognize_formula", "image": tmp_path},
                    timeout_sec=300.0,
                )
            elif mode == "text":
                result = self._send_worker_request(
                    {
                        "action": "recognize_text",
                        "image": tmp_path,
                    },
                    timeout_sec=600.0,
                )
            else:
                result = self._send_worker_request(
                    {
                        "action": "recognize_mixed",
                        "image": tmp_path,
                    },
                    timeout_sec=600.0,
                )
            self.last_used_model = model
            result["model"] = model
            result["mode"] = mode
            result["image_size"] = [int(image_rgb.width), int(image_rgb.height)]
            result["text"] = str(result.get("text", "") or "").strip()
            return result
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

    def predict(self, pil_img: Image.Image, model_name: str = "mathcraft") -> str:
        result = self.predict_result(pil_img, model_name=model_name)
        return str(result.get("text", "") or "").strip()

    def __del__(self):
        try:
            self._stop_mathcraft_worker()
        except Exception:
            pass
