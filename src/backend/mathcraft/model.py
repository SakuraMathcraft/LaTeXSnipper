# coding: utf-8

from __future__ import annotations

import logging
from collections import deque
import json
import os
import queue
import re
import subprocess
import tempfile
import threading
from typing import Any

from PIL import Image
from PyQt6.QtCore import QObject, pyqtSignal
from runtime.installed_resources import installed_resources, worker_environment, worker_command
from mathcraft_ocr.protocol import WORKER_PROTOCOL, MODEL_FORMAT, validate_response
from runtime.exception_diagnostics import format_exception_diagnostics
from backend.mathcraft.diagnostics import classify_mathcraft_failure
from backend.mathcraft.process_environment import _failed_warmup_component_details
from runtime.processes import hidden_subprocess_kwargs

logger = logging.getLogger(f"latexsnipper.{__name__}")


os.environ.setdefault("ORT_DISABLE_AZURE", "1")


MODEL_MODES = {
    "mathcraft": "formula",
    "mathcraft_text": "text",
    "mathcraft_mixed": "mixed",
}

FORMULA_RECOGNITION_MAX_NEW_TOKENS = 512
EMPTY_IMAGE_STD_THRESHOLD = 2.5
EMPTY_IMAGE_FOREGROUND_RATIO_THRESHOLD = 0.0015


class _MathCraftWorkerError(RuntimeError):
    """An OCR worker failure with its child-process traceback preserved for logs."""

    def __init__(self, error_type: str, message: str, remote_traceback: str = "") -> None:
        label = f"{error_type}: {message}" if error_type else message
        super().__init__(label or "MathCraft OCR 运行错误")
        self.remote_traceback = str(remote_traceback or "").strip()


def _looks_like_empty_ocr_input(image: Image.Image) -> bool:
    """Return True for near-uniform images with no meaningful foreground."""
    if image.width <= 0 or image.height <= 0:
        return True
    sample = image.convert("L")
    max_edge = 384
    if max(sample.size) > max_edge:
        scale = max_edge / max(sample.size)
        sample = sample.resize(
            (max(1, int(sample.width * scale)), max(1, int(sample.height * scale))),
            Image.Resampling.BILINEAR,
        )
    pixels = sample.get_flattened_data()
    if not pixels:
        return True
    mean = sum(pixels) / len(pixels)
    variance = sum((value - mean) ** 2 for value in pixels) / len(pixels)
    std = variance**0.5
    if std <= EMPTY_IMAGE_STD_THRESHOLD:
        return True
    foreground = sum(1 for value in pixels if abs(value - mean) >= 32)
    return (foreground / len(pixels)) < EMPTY_IMAGE_FOREGROUND_RATIO_THRESHOLD


_LATEX_ATOM_RE = re.compile(
    r"(\\[A-Za-z]+(?:\s*_\s*\{[^{}]{1,24}\})?|[A-Za-z0-9]+(?:\s*_\s*\{[^{}]{1,24}\})?)"
)


def _looks_like_degenerate_formula_text(text: str) -> bool:
    """Detect decoder loops such as the same LaTeX atom repeated many times."""
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(normalized) < 80:
        return False
    atoms = _LATEX_ATOM_RE.findall(normalized)
    if len(atoms) < 24:
        return False
    counts: dict[str, int] = {}
    for atom in atoms:
        key = re.sub(r"\s+", "", atom)
        counts[key] = counts.get(key, 0) + 1
    most_common = max(counts.values(), default=0)
    return most_common >= 16 and most_common / max(1, len(atoms)) >= 0.45


def _empty_recognition_result(model: str, mode: str, image: Image.Image, reason: str) -> dict[str, Any]:
    return {
        "text": "",
        "score": 0.0,
        "model": model,
        "mode": mode,
        "image_size": [int(image.width), int(image.height)],
        "empty_reason": reason,
    }


class ModelWrapper(QObject):
    """MathCraft-only internal OCR wrapper."""

    status_signal = pyqtSignal(str)

    def __init__(self, default_model: str | None = None, auto_warmup: bool = True):
        super().__init__()
        self.device = "cpu"
        self.provider_info: dict[str, object] = {}
        self.runtime_info: dict[str, object] = {}
        self._default_model = self._normalize_model_name(default_model or "mathcraft")
        self._worker: subprocess.Popen | None = None
        self._worker_lock = threading.Lock()
        self._request_lock = threading.Lock()
        self._request_seq = 0
        self._ready = False
        self._import_failed = False
        self._last_error = ""
        self._failure_info: dict[str, str] = {}
        self._resources = None
        self._handshake_complete = False
        self._ready_modes: set[str] = set()
        self._stderr_lock = threading.Lock()
        self._worker_stderr_tail: deque[str] = deque(maxlen=80)
        self._stderr_thread: threading.Thread | None = None
        self._cache_events_seen: set[str] = set()

        if auto_warmup:
            self.warmup()

    def _emit(self, msg: str, *, level: int = logging.INFO) -> None:
        logger.log(level, "%s", msg)
        try:
            self.status_signal.emit(f"[{logging.getLevelName(level)}] {msg}")
        except Exception:
            pass

    def _build_subprocess_env(self) -> dict:
        return worker_environment(self._resources)

    def _normalize_model_name(self, model_name: str | None) -> str:
        model = str(model_name or "").strip().lower()
        if model not in MODEL_MODES:
            raise ValueError(f"Unsupported MathCraft model mode: {model_name!r}")
        return model

    def _mode_for_model(self, model_name: str | None) -> str:
        model = self._normalize_model_name(model_name)
        return MODEL_MODES[model]

    def set_default_model(self, model_name: str | None) -> None:
        self._default_model = self._normalize_model_name(model_name or "mathcraft")

    def _next_request_id(self) -> str:
        self._request_seq += 1
        return f"mathcraft-{self._request_seq}"

    def _worker_argv(self) -> list[str]:
        self._resources = installed_resources()
        return worker_command(self._resources)

    def _worker_stderr_text(self, limit: int = 4000) -> str:
        with self._stderr_lock:
            text = "\n".join(self._worker_stderr_tail)
        return text.strip()[-limit:]

    def _emit_cache_event_once(self, event: str) -> None:
        event = str(event or "").strip()
        if not event or event in self._cache_events_seen:
            return
        self._cache_events_seen.add(event)
        logger.debug("MathCraft model cache: %s", event)
        try:
            self.status_signal.emit(f"[INFO] MathCraft model cache: {event}")
        except Exception:
            pass

    def _start_worker_stderr_pump(self, proc: subprocess.Popen) -> None:
        stderr = proc.stderr
        if stderr is None:
            return
        tail = self._worker_stderr_tail

        def _pump() -> None:
            try:
                for raw_line in stderr:
                    line = str(raw_line or "").strip()
                    if not line:
                        continue
                    with self._stderr_lock:
                        tail.append(line)
                    prefix = "[MATHCRAFT_CACHE]"
                    if line.startswith(prefix):
                        self._emit_cache_event_once(line[len(prefix):].strip())
                    else:
                        logger.info("MathCraft worker stderr pid=%s: %s", proc.pid, line)
            except (OSError, ValueError) as exc:
                logger.warning("MathCraft worker stderr read failed: %s", exc)

        self._stderr_thread = threading.Thread(target=_pump, daemon=True)
        self._stderr_thread.start()

    def _worker_transport_error(self, proc: subprocess.Popen, message: str) -> RuntimeError:
        # Snapshot the natural exit code before cleanup can terminate a live process.
        try:
            exit_code = proc.wait(timeout=0.2)
        except subprocess.TimeoutExpired:
            exit_code = None
        self.stop()
        status = "running before cleanup" if exit_code is None else str(exit_code)
        if exit_code is not None:
            status += f" (0x{exit_code & 0xFFFFFFFF:08X})"
        detail = self._worker_stderr_text()
        return RuntimeError(
            f"{message}; pid={proc.pid}; exit_code={status}"
            + (f"\nWorker stderr:\n{detail}" if detail else "")
        )

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
                    self._worker_stderr_tail = deque(maxlen=80)
                proc = subprocess.Popen(
                    self._worker_argv(),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=self._build_subprocess_env(),
                    **hidden_subprocess_kwargs(),
                )
                self._worker = proc
                self._handshake_complete = False
                self._start_worker_stderr_pump(proc)
                return True
            except Exception as exc:
                self._set_error(str(exc))
                self._emit(f"MathCraft OCR 运行进程启动失败:\n{format_exception_diagnostics(exc)}", level=logging.ERROR)
                self._worker = None
                return False

    def _send_worker_request(self, payload: dict[str, Any], timeout_sec: float | None = 300.0) -> dict[str, Any]:
        if not self._ensure_worker():
            raise RuntimeError(self._last_error or "MathCraft OCR 运行进程启动失败")
        proc = self._worker
        if proc is None or proc.stdin is None or proc.stdout is None:
            raise RuntimeError("MathCraft OCR 运行进程管道不可用")

        if payload.get('action') != 'hello' and not self._handshake_complete:
            hello = self._send_worker_request({'action': 'hello'}, timeout_sec=30)
            if hello.get('worker_protocol') != WORKER_PROTOCOL or hello.get('model_format') != MODEL_FORMAT:
                self.stop()
                raise RuntimeError('MathCraft worker contract mismatch')
            if self._resources is not None:
                from runtime.distribution_manifest import read_json

                details = read_json(self._resources.root / 'inference/runtime.json')
                if any(hello.get(key) != details[key] for key in ('python_version', 'ort_version')):
                    self.stop()
                    raise RuntimeError('MathCraft worker runtime versions do not match the installation')
            self._handshake_complete = True
            self.runtime_info = dict(hello)
        request = dict(payload)
        request['protocol'] = WORKER_PROTOCOL
        request["id"] = request.get("id") or self._next_request_id()
        with self._request_lock:
            try:
                proc.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
                proc.stdin.flush()
            except Exception as exc:
                raise self._worker_transport_error(proc, f"MathCraft OCR 请求发送失败: {exc}") from exc
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
                raise self._worker_transport_error(proc, f"MathCraft OCR 运行进程超时（>{timeout_sec:.0f}s）") from exc
            if isinstance(line_or_exc, BaseException):
                raise self._worker_transport_error(proc, f"MathCraft OCR 响应读取失败: {line_or_exc}") from line_or_exc
            line = line_or_exc

        if not line:
            raise self._worker_transport_error(proc, "MathCraft OCR 运行进程没有返回结果")
        try:
            response = validate_response(json.loads(line), request["id"])
        except Exception as exc:
            raise self._worker_transport_error(proc, f"MathCraft OCR 返回了无效响应: {exc}; {line[:300]}") from exc
        if not response.get("ok"):
            err = response.get("error", {})
            if isinstance(err, dict):
                raise _MathCraftWorkerError(
                    str(err.get("type") or "").strip(),
                    str(err.get("message") or "").strip(),
                    str(err.get("traceback") or "").strip(),
                )
            raise RuntimeError(str(err or "MathCraft OCR 运行错误"))
        return response["result"]

    def _set_error(self, detail: str) -> dict[str, str]:
        info = classify_mathcraft_failure(detail)
        self._last_error = str(info.get("user_message", "") or detail or "").strip()
        self._failure_info = info
        self._import_failed = True
        self._ready = False
        self.provider_info = {}
        return info

    def _clear_error(self) -> None:
        self._last_error = ""
        self._failure_info = {}
        self._import_failed = False

    def stop(self) -> None:
        self.runtime_info = {}
        proc = self._worker
        self._worker = None
        if not proc:
            self._ready = False
            self.provider_info = {}
            return
        try:
            if proc.poll() is None:
                proc.terminate()
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=1)
        except (OSError, subprocess.TimeoutExpired) as exc:
            self._emit(f"MathCraft worker cleanup pid={proc.pid}: {exc}", level=logging.WARNING)
        if self._stderr_thread is not None:
            self._stderr_thread.join(timeout=1)
            if self._stderr_thread.is_alive():
                self._emit(f"MathCraft worker stderr drain incomplete pid={proc.pid}", level=logging.WARNING)
            self._stderr_thread = None
        self._ready = False
        self._ready_modes.clear()
        self.provider_info = {}

    def warmup(self, model_name: str | None = None) -> bool:
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
                traces = [
                    f"Component {status.get('model_id', 'unknown')}:\n{status['traceback']}"
                    for status in result.get("component_statuses", [])
                    if isinstance(status, dict) and status.get("traceback")
                ]
                raise _MathCraftWorkerError("WarmupFailed", detail, "\n".join(traces))
            provider = result.get("provider_info", {})
            if isinstance(provider, dict):
                self.provider_info = dict(provider)
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
                "MathCraft OCR 已就绪"
                f"{f'（实际后端: {active_provider}）' if active_provider else ''}"
            )
            return True
        except Exception as exc:
            info = self._set_error(str(exc))
            self._emit(
                f"MathCraft OCR 预热失败 code={info['code']} profile={mode}\n"
                f"{info['log_message']}\n{format_exception_diagnostics(exc)}",
                level=logging.ERROR,
            )
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

    def get_failure_info(self) -> dict[str, str]:
        return dict(self._failure_info)

    def get_status_text(self) -> str:
        if self._import_failed:
            return f"model load failed: {self._last_error or 'MathCraft OCR not ready'}"
        if self._ready:
            return f"model ready (MathCraft, device={self.device})"
        return "model not loaded"

    def predict_result(self, pil_img: Image.Image, model_name: str = "mathcraft") -> dict[str, Any]:
        model = self._normalize_model_name(model_name)
        mode = self._mode_for_model(model)
        if mode not in self._ready_modes and not self.warmup(model):
            raise RuntimeError(self._last_error or "MathCraft OCR not ready")

        tmp_path = ""
        try:
            image_rgb = pil_img.convert("RGB")
            if _looks_like_empty_ocr_input(image_rgb):
                return _empty_recognition_result(model, mode, image_rgb, "empty_image")
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = tmp.name
                image_rgb.save(tmp, format="PNG", compress_level=1)
            if mode == "formula":
                result = self._send_worker_request(
                    {
                        "action": "recognize_formula",
                        "image": tmp_path,
                        "max_new_tokens": FORMULA_RECOGNITION_MAX_NEW_TOKENS,
                    },
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
                        "max_formula_new_tokens": FORMULA_RECOGNITION_MAX_NEW_TOKENS,
                    },
                    timeout_sec=600.0,
                )
            result["model"] = model
            result["mode"] = mode
            result["image_size"] = [int(image_rgb.width), int(image_rgb.height)]
            result["text"] = str(result.get("text", "") or "").strip()
            if mode == "formula" and _looks_like_degenerate_formula_text(result["text"]):
                return _empty_recognition_result(model, mode, image_rgb, "degenerate_formula_output")
            return result
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

    def predict(self, pil_img: Image.Image, model_name: str = "mathcraft") -> str:
        result = self.predict_result(pil_img, model_name=model_name)
        text = str(result.get("text", "") or "").strip()
        mode = str(result["mode"]).strip().lower()
        # Low-confidence handling: show a hint when the score is very low and output is empty or suspicious.
        score = result.get("score")
        if isinstance(score, (int, float)) and float(score) < 0.2:
            if not text:
                if mode == "text":
                    return "未识别到文本内容"
                if mode == "mixed":
                    return "未检测到可识别内容"
                return "未识别到公式内容"
            return f"低置信度: {text}"
        # Mixed mode has no score field; empty text means nothing recognizable was detected.
        if not text:
            if mode == "text":
                return "未识别到文本内容"
            if mode == "formula":
                return "未识别到公式内容"
            return "未检测到可识别内容"
        return text

    def __del__(self):
        try:
            self.stop()
        except Exception:
            pass

    def restart(self) -> None:
        """Reset the inference process and readiness through its owner."""
        self.stop()
        self._clear_error()
