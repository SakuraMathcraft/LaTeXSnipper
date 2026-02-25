import os
import tempfile
import time

from PIL import Image
from PyQt6.QtCore import QObject, pyqtSignal

from backend.daemon_client import LocalDaemonClient
from backend.rpc_contract import METHOD_WARMUP, TASK_KIND_PREDICT_IMAGE, TASK_KIND_PREDICT_PDF


class DaemonModelWrapper(QObject):
    """Stage-1 adapter: keep old ModelWrapper interface, execute via local daemon RPC."""

    status_signal = pyqtSignal(str)
    daemon_event_signal = pyqtSignal(dict)
    daemon_error_signal = pyqtSignal(dict)

    def __init__(self, default_model: str | None = None):
        super().__init__()
        self.device = "cpu"
        self.torch = None
        self.last_used_model = None
        self._pix2text_import_failed = False
        self._pix2text_subprocess_ready = False
        self._default_model = (default_model or "pix2text").lower()
        if not self._default_model.startswith("pix2text"):
            self._default_model = "pix2text"
        self._last_error: dict | None = None
        self._client = LocalDaemonClient(model_name=self._default_model, log_cb=self._on_daemon_log)
        self._emit("[INFO] daemon mode enabled (stage1)")
        self._emit_event("adapter_init", model=self._default_model)
        if not self._client.start():
            self._pix2text_import_failed = True
            self._emit("[WARN] daemon startup failed")
            self._emit_error(
                "daemon_start_failed",
                error=(self._client.last_error or {}).get("error", "unknown"),
                error_type=(self._client.last_error or {}).get("error_type", "StartError"),
            )
        else:
            self._emit_event("daemon_started", pid=getattr(self._client.proc, "pid", None))
            self._lazy_load_pix2text()

    def _emit(self, msg: str) -> None:
        try:
            print(msg)
        except Exception:
            pass
        try:
            self.status_signal.emit(msg)
        except Exception:
            pass

    def _on_daemon_log(self, line: str) -> None:
        # daemon 原始日志仅输出到运行日志，不进入 UI 模型状态文本。
        try:
            print(line, flush=True)
        except Exception:
            pass

    def _emit_event(self, event: str, **fields) -> None:
        payload = {
            "ts": time.time(),
            "event": str(event),
            "model": "pix2text",
        }
        payload.update({str(k): v for k, v in (fields or {}).items()})
        try:
            self.daemon_event_signal.emit(payload)
        except Exception:
            pass
        try:
            print(f"[DAEMON_CLIENT_EVT] {payload}", flush=True)
        except Exception:
            pass

    def _emit_error(self, event: str, *, error: str, error_type: str = "RuntimeError", **fields) -> None:
        payload = {
            "ts": time.time(),
            "event": str(event),
            "model": "pix2text",
            "error": str(error or "unknown"),
            "error_type": str(error_type or "RuntimeError"),
        }
        payload.update({str(k): v for k, v in (fields or {}).items()})
        self._last_error = payload
        try:
            self.daemon_error_signal.emit(payload)
        except Exception:
            pass
        self._emit(f"[ERROR] daemon {payload['event']}: {payload['error']} ({payload['error_type']})")

    def _stop_pix2text_worker(self):
        try:
            self._emit_event("daemon_stop_requested")
            self._client.stop(force=True)
        except Exception:
            pass
        self._pix2text_subprocess_ready = False
        self._emit_event("daemon_stopped")

    def _lazy_load_pix2text(self):
        try:
            resp = self._client.request(METHOD_WARMUP, {}, timeout_sec=120.0)
            ok = bool(resp.get("ok"))
            self._pix2text_subprocess_ready = ok
            self._pix2text_import_failed = not ok
            if ok:
                self._emit("[INFO] daemon warmup ok")
                self._emit_event("warmup_ok", ready=bool(resp.get("ready", False)))
            else:
                self._emit(f"[WARN] daemon warmup failed: {resp.get('error', 'unknown')}")
                self._emit_error(
                    "warmup_failed",
                    error=str(resp.get("error", "unknown")),
                    error_type=str(resp.get("error_type", "RemoteError")),
                )
            return ok
        except Exception as e:
            self._pix2text_subprocess_ready = False
            self._pix2text_import_failed = True
            self._emit(f"[WARN] daemon warmup exception: {e}")
            self._emit_error("warmup_exception", error=str(e), error_type=e.__class__.__name__)
            return False

    def is_ready(self) -> bool:
        return self.is_pix2text_ready()

    def is_pix2text_ready(self) -> bool:
        return bool(self._pix2text_subprocess_ready)

    def is_model_ready(self, model_name: str) -> bool:
        return self.is_pix2text_ready() if (model_name or "").startswith("pix2text") else False

    def get_error(self) -> str | None:
        if self._pix2text_import_failed:
            return "pix2text daemon not ready"
        return None

    def get_status_text(self) -> str:
        if self._pix2text_import_failed:
            return "model load failed: daemon not ready"
        if self._pix2text_subprocess_ready:
            return "model ready (daemon)"
        return "model not loaded"

    def predict(self, pil_img: Image.Image, model_name: str = "pix2text") -> str:
        self._last_error = None
        if not self._pix2text_subprocess_ready:
            self._lazy_load_pix2text()
        if not self._pix2text_subprocess_ready:
            raise RuntimeError("pix2text not ready")

        model = (model_name or "pix2text").lower()
        if not model.startswith("pix2text"):
            model = "pix2text"
        self.last_used_model = model

        tmp_path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = tmp.name
                pil_img.save(tmp, format="PNG")
            task_id = self._client.submit_task(
                TASK_KIND_PREDICT_IMAGE,
                {"image_path": tmp_path, "model_name": model},
                timeout_sec=15.0,
            )
            self._emit_event("task_submitted", task_kind=TASK_KIND_PREDICT_IMAGE, task_id=task_id, model_name=model)
            task = self._client.wait_task(task_id, timeout_sec=300.0, poll_interval_sec=0.15)
            output = task.get("output", {}) if isinstance(task, dict) else {}
            result = str((output or {}).get("result", "") or "")
            if not result and isinstance(output, dict) and ("error" in output):
                raise RuntimeError(str(output.get("error", "daemon predict failed")))
            self._emit_event("predict_ok", model_name=model, result_len=len(result))
            return result
        except Exception as e:
            if str(e).strip() == "已取消":
                self._emit_event("task_cancelled", task_kind="predict_image", model_name=model)
                raise RuntimeError("已取消")
            if self._last_error is None:
                self._emit_error("predict_exception", error=str(e), error_type=e.__class__.__name__, model_name=model)
            raise
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

    def predict_pdf(
        self,
        pdf_path: str,
        max_pages: int,
        model_name: str,
        output_format: str,
        dpi: int = 200,
        progress_cb=None,
        cancel_cb=None,
    ) -> str:
        self._last_error = None
        if not self._pix2text_subprocess_ready:
            self._lazy_load_pix2text()
        if not self._pix2text_subprocess_ready:
            raise RuntimeError("pix2text not ready")

        model = (model_name or "pix2text").lower()
        if not model.startswith("pix2text"):
            model = "pix2text"
        self.last_used_model = model

        task_id = ""
        try:
            task_id = self._client.submit_task(
                TASK_KIND_PREDICT_PDF,
                {
                    "pdf_path": str(pdf_path or ""),
                    "max_pages": int(max(max_pages, 1)),
                    "model_name": model,
                    "output_format": str(output_format or "markdown"),
                    "dpi": int(max(dpi, 72)),
                },
                timeout_sec=20.0,
            )
            self._emit_event(
                "task_submitted",
                task_kind=TASK_KIND_PREDICT_PDF,
                task_id=task_id,
                model_name=model,
                max_pages=int(max(max_pages, 1)),
                dpi=int(max(dpi, 72)),
            )

            def _on_progress(cur: int, total: int, task: dict):
                self._emit_event(
                    "task_progress",
                    task_kind=TASK_KIND_PREDICT_PDF,
                    task_id=task_id,
                    current=int(cur),
                    total=int(total),
                )
                if callable(progress_cb):
                    try:
                        progress_cb(int(cur), int(total))
                    except Exception:
                        pass

            task = self._client.wait_task(
                task_id,
                timeout_sec=1800.0,
                poll_interval_sec=0.2,
                progress_cb=_on_progress,
                cancel_cb=cancel_cb,
            )
            output = task.get("output", {}) if isinstance(task, dict) else {}
            content = str((output or {}).get("content", "") or "")
            if not content.strip():
                raise RuntimeError("识别结果为空")
            self._emit_event(
                "predict_pdf_ok",
                task_id=task_id,
                model_name=model,
                content_len=len(content),
                pages=int((output or {}).get("pages", 0) or 0),
            )
            return content.strip()
        except Exception as e:
            if str(e).strip() == "已取消":
                self._emit_event("task_cancelled", task_kind="predict_pdf", task_id=task_id, model_name=model)
                raise RuntimeError("已取消")
            if self._last_error is None:
                self._emit_error(
                    "predict_pdf_exception",
                    error=str(e),
                    error_type=e.__class__.__name__,
                    task_id=task_id,
                    model_name=model,
                )
            raise
