# coding: utf-8

from __future__ import annotations

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
    "mathcraft_text": "mixed",
    "mathcraft_mixed": "mixed",
    "mathcraft_page": "mixed",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _subprocess_creationflags() -> int:
    if os.name != "nt":
        return 0
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))


def get_deps_python() -> str:
    pyexe = os.environ.get("LATEXSNIPPER_PYEXE", "")
    if pyexe and os.path.exists(pyexe):
        return pyexe
    if getattr(sys, "frozen", False):
        print("[WARN] packaged mode: deps python not configured, fallback to current runtime")
    return sys.executable


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
    if "not ready" in lower and "missing" in lower:
        return _pack(
            "MODEL_CACHE_INCOMPLETE",
            "模型缓存不完整",
            "MathCraft OCR 模型缓存不完整，请补齐模型权重后重试。",
            f"MathCraft 模型缓存不完整: {raw[:300]}",
        )
    if "cuda" in lower and (
        "createexecutionproviderinstance" in lower
        or "cuda_path is set" in lower
        or "cuda wasn't able to be loaded" in lower
    ):
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
            "MathCraft OCR worker 响应超时，请稍后重试或检查模型运行环境。",
            "MathCraft worker 超时，需要检查模型初始化耗时、图片大小和运行环境。",
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
        self.torch = None
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
        self._provider = "auto"

        self._emit("[INFO] internal OCR runtime: MathCraft worker")
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
        for key in ("PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP", "PYTHONEXECUTABLE"):
            env.pop(key, None)
        env["PYTHONNOUSERSITE"] = "1"
        env["PYTHONPATH"] = str(_repo_root())
        return env

    def _normalize_model_name(self, model_name: str | None) -> str:
        model = str(model_name or "mathcraft").strip().lower()
        if model in MODEL_MODES:
            return model
        return "mathcraft"

    def _mode_for_model(self, model_name: str | None) -> str:
        model = self._normalize_model_name(model_name)
        return MODEL_MODES.get(model, "formula")

    def _next_request_id(self) -> str:
        self._request_seq += 1
        return f"mathcraft-{self._request_seq}"

    def _worker_argv(self) -> list[str]:
        repo = str(_repo_root())
        code = (
            "import sys; "
            f"sys.path.insert(0, {repo!r}); "
            "from mathcraft_ocr.cli import main; "
            f"raise SystemExit(main(['worker', '--provider', {self._provider!r}]))"
        )
        return [get_deps_python(), "-u", "-c", code]

    def _ensure_worker(self) -> bool:
        proc = self._worker
        if proc is not None and proc.poll() is None:
            return True
        with self._worker_lock:
            proc = self._worker
            if proc is not None and proc.poll() is None:
                return True
            try:
                self._worker = subprocess.Popen(
                    self._worker_argv(),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=self._build_subprocess_env(),
                    creationflags=_subprocess_creationflags(),
                )
                return True
            except Exception as exc:
                self._set_error(str(exc))
                self._emit(f"[ERROR] MathCraft worker start failed: {exc}")
                self._worker = None
                return False

    def _send_worker_request(self, payload: dict[str, Any], timeout_sec: float = 300.0) -> dict[str, Any]:
        if not self._ensure_worker():
            raise RuntimeError(self._last_error or "MathCraft worker start failed")
        proc = self._worker
        if proc is None or proc.stdin is None or proc.stdout is None:
            raise RuntimeError("MathCraft worker pipe is not available")

        request = dict(payload)
        request["id"] = request.get("id") or self._next_request_id()
        with self._request_lock:
            try:
                proc.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
                proc.stdin.flush()
            except Exception as exc:
                self._stop_mathcraft_worker()
                raise RuntimeError(f"MathCraft worker request failed: {exc}") from exc
            lines: queue.Queue[str | BaseException] = queue.Queue(maxsize=1)

            def _readline() -> None:
                try:
                    lines.put(proc.stdout.readline())
                except BaseException as exc:
                    lines.put(exc)

            reader = threading.Thread(target=_readline, daemon=True)
            reader.start()
            try:
                line_or_exc = lines.get(timeout=max(float(timeout_sec), 1.0))
            except queue.Empty as exc:
                self._stop_mathcraft_worker()
                raise RuntimeError(f"MathCraft worker timeout after {timeout_sec:.0f}s") from exc
            if isinstance(line_or_exc, BaseException):
                self._stop_mathcraft_worker()
                raise RuntimeError(f"MathCraft worker response failed: {line_or_exc}") from line_or_exc
            line = line_or_exc

        if not line:
            self._stop_mathcraft_worker()
            raise RuntimeError("MathCraft worker exited without response")
        try:
            response = json.loads(line)
        except Exception as exc:
            raise RuntimeError(f"MathCraft worker returned invalid JSON: {line[:300]}") from exc
        if not response.get("ok"):
            err = response.get("error", {})
            message = err.get("message") if isinstance(err, dict) else str(err)
            raise RuntimeError(str(message or "MathCraft worker error"))
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

    def _lazy_load_mathcraft(self) -> bool:
        if self._ready:
            return True
        try:
            mode = self._mode_for_model(self._default_model)
            result = self._send_worker_request({"action": "warmup", "profile": mode}, timeout_sec=300.0)
            ready = bool(result.get("ready"))
            if not ready:
                missing = result.get("missing_models", [])
                unsupported = result.get("unsupported_models", [])
                raise RuntimeError(
                    f"MathCraft runtime is not ready: missing={missing}, unsupported={unsupported}"
                )
            provider = result.get("provider_info", {})
            if isinstance(provider, dict):
                self.device = str(provider.get("device") or self.device or "cpu")
                active_provider = str(provider.get("active_provider") or "")
            else:
                active_provider = ""
            self._ready = True
            self._clear_error()
            self._emit(
                "[INFO] MathCraft OCR worker ready"
                f"{f' ({active_provider})' if active_provider else ''}"
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
            self._mode_for_model(model_name)
        except Exception:
            return False
        return self._ready

    def get_error(self) -> str | None:
        return self._last_error if self._import_failed else None

    def get_status_text(self) -> str:
        if self._import_failed:
            return f"model load failed: {self._last_error or 'MathCraft OCR not ready'}"
        if self._ready:
            return f"model ready (MathCraft, device={self.device})"
        return "model not loaded"

    def predict(self, pil_img: Image.Image, model_name: str = "mathcraft") -> str:
        model = self._normalize_model_name(model_name)
        mode = self._mode_for_model(model)
        if not self._ready and not self._lazy_load_mathcraft():
            raise RuntimeError(self._last_error or "MathCraft OCR not ready")

        tmp_path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = tmp.name
                pil_img.convert("RGB").save(tmp, format="PNG")
            if mode == "formula":
                result = self._send_worker_request(
                    {"action": "recognize_formula", "image": tmp_path},
                    timeout_sec=300.0,
                )
                text = str(result.get("text", "") or "")
            else:
                result = self._send_worker_request(
                    {
                        "action": "recognize_mixed",
                        "image": tmp_path,
                        "ocr_profile": "auto",
                    },
                    timeout_sec=600.0,
                )
                text = str(result.get("text", "") or "")
            self.last_used_model = model
            return text.strip()
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

    def __del__(self):
        try:
            self._stop_mathcraft_worker()
        except Exception:
            pass
