"""Bounded FIFO recognition coordinator backed by one resident worker."""

from __future__ import annotations

import queue
import secrets
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from integration.automation.contracts import AutomationApiError, AutomationLimits, DEFAULT_LIMITS
from recognition.image_preprocess import optimize_mathcraft_input_image
from recognition.jobs.models import (
    JobSource,
    JobState,
    RecognitionItem,
    RecognitionItemInput,
    RecognitionJob,
    utc_now_iso,
)
from recognition.jobs.executors import ExternalRecognitionExecutor


_MODE_TO_MODEL = {"formula": "mathcraft", "text": "mathcraft_text", "mixed": "mathcraft_mixed"}
_BACKENDS = ("mathcraft", "external")
_STOP = object()


@dataclass(slots=True)
class _ExternalOperation:
    callback: Callable[[], Any]
    event: threading.Event = field(default_factory=threading.Event)
    result: Any = None
    error: BaseException | None = None


class RecognitionJobCoordinator:
    def __init__(
        self,
        predictor: Callable[[Any, str], str] | Any,
        *,
        limits: AutomationLimits = DEFAULT_LIMITS,
        clock: Callable[[], float] = time.monotonic,
        external_config_provider: Callable[[], Any | None] | None = None,
        external_predictor: Callable[[Any, Any], str] | None = None,
        autostart: bool = True,
    ) -> None:
        self._predictor = predictor
        self._limits = limits
        self._clock = clock
        self._lock = threading.RLock()
        self._jobs: OrderedDict[str, RecognitionJob] = OrderedDict()
        self._expired_ids: OrderedDict[str, float] = OrderedDict()
        self._queued_count = 0
        self._active_image_memory = 0
        self._queues = {
            backend: queue.Queue(maxsize=limits.max_queued_jobs) for backend in _BACKENDS
        }
        self._stopping = False
        self._external_executor = ExternalRecognitionExecutor(
            external_config_provider,
            external_predictor,
        )
        self._workers = {
            "mathcraft": threading.Thread(
                target=self._worker_main,
                args=("mathcraft",),
                name="MathCraftRecognitionWorker",
                daemon=True,
            ),
            "external": threading.Thread(
                target=self._worker_main,
                args=("external",),
                name="ExternalRecognitionWorker",
                daemon=True,
            ),
        }
        if autostart:
            self.start()

    def start(self) -> None:
        with self._lock:
            if self._stopping:
                return
            for worker in self._workers.values():
                if not worker.is_alive():
                    worker.start()

    @property
    def model_available(self) -> bool:
        return self._predictor is not None

    @property
    def external_available(self) -> bool:
        return self._external_executor.available()

    def backend_available(self, backend: str) -> bool:
        if backend == "mathcraft":
            return self.model_available
        if backend == "external":
            return self.external_available
        return False

    def _validate_mode_capability(self, backend: str, mode: str) -> None:
        if mode not in _MODE_TO_MODEL:
            raise AutomationApiError(400, "invalid_mode", "不支持该识别模式。")
        target = self._predictor if backend == "mathcraft" else self._external_executor
        supports_mode = getattr(target, "supports_mode", None)
        if callable(supports_mode) and not bool(supports_mode(mode)):
            raise AutomationApiError(422, "mode_unsupported", "当前识别后端不支持该模式。")

    def submit(
        self,
        images: Sequence[RecognitionItemInput],
        *,
        principal_id: str,
        source: JobSource,
        mode: str,
        timeout_seconds: float,
        input_type: str = "image_upload",
        backend: str = "mathcraft",
        external_config: Any | None = None,
    ) -> dict[str, Any]:
        if not images:
            raise AutomationApiError(400, "invalid_request", "至少需要一张图片。")
        if len(images) > self._limits.max_batch_items:
            raise AutomationApiError(413, "batch_too_large", "批量图片数量超过限制。")
        normalized_backend = str(backend or "mathcraft").strip().lower()
        if normalized_backend not in _BACKENDS:
            raise AutomationApiError(400, "invalid_backend", "不支持该识别后端。")
        self._validate_mode_capability(normalized_backend, mode)
        backend_config = None
        if normalized_backend == "external":
            backend_config = self._external_executor.snapshot(mode, external_config)
        elif not self.model_available:
            raise AutomationApiError(503, "model_unavailable", "MathCraft 识别当前不可用。")
        job = RecognitionJob(
            id=secrets.token_urlsafe(24),
            principal_id=principal_id,
            source=source,
            input_type=input_type,
            backend=normalized_backend,
            mode=mode,
            timeout_seconds=timeout_seconds,
            state=JobState.QUEUED,
            images=list(images),
            items=[RecognitionItem(index=index, filename=item.filename) for index, item in enumerate(images)],
            backend_config=backend_config,
            memory_reserved=True,
            created_monotonic=self._clock(),
            queued_at=utc_now_iso(),
        )
        with self._lock:
            self._purge_locked()
            if self._stopping:
                raise AutomationApiError(503, "model_unavailable", "识别服务正在停止。")
            if self._queued_count >= self._limits.max_queued_jobs:
                raise AutomationApiError(503, "queue_full", "识别队列已满。")
            if self._active_image_memory + job.memory_bytes > self._limits.max_queued_image_bytes:
                raise AutomationApiError(503, "queue_full", "识别任务的图片内存已达到上限。")
            self._jobs[job.id] = job
            self._queued_count += 1
            self._active_image_memory += job.memory_bytes
            try:
                self._queues[normalized_backend].put_nowait(job.id)
            except queue.Full as exc:
                self._jobs.pop(job.id, None)
                self._queued_count -= 1
                self._active_image_memory -= job.memory_bytes
                job.memory_reserved = False
                raise AutomationApiError(503, "queue_full", "识别队列已满。") from exc
            return job.snapshot()

    def create_next_result_job(
        self,
        *,
        principal_id: str,
        source: JobSource,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        job = RecognitionJob(
            id=secrets.token_urlsafe(24),
            principal_id=principal_id,
            source=source,
            input_type="next_result",
            backend="desktop",
            mode="current",
            timeout_seconds=timeout_seconds,
            state=JobState.AWAITING_RESULT,
            images=[],
            items=[RecognitionItem(index=0, filename="", state="awaiting_result")],
            created_monotonic=self._clock(),
        )
        with self._lock:
            self._purge_locked()
            if any(existing.state is JobState.AWAITING_RESULT for existing in self._jobs.values()):
                raise AutomationApiError(409, "next_result_busy", "已有客户端正在等待下一次识别结果。")
            active_count = sum(
                job.state not in (JobState.COMPLETED, JobState.FAILED, JobState.CANCELED)
                for job in self._jobs.values()
            )
            if active_count >= self._limits.max_queued_jobs:
                raise AutomationApiError(503, "queue_full", "识别队列已满。")
            self._jobs[job.id] = job
            return job.snapshot()

    def publish_next_result(self, text: str, *, backend: str, mode: str) -> bool:
        with self._lock:
            self._purge_locked()
            job = next((item for item in self._jobs.values() if item.state is JobState.AWAITING_RESULT), None)
            if job is None:
                return False
            job.backend = backend
            job.mode = mode
            job.items[0].state = "completed"
            job.items[0].text = str(text or "").strip()
            self._finish_locked(job, JobState.COMPLETED)
            return True

    def fail_next_result(self, message: str) -> bool:
        with self._lock:
            self._purge_locked()
            job = next((item for item in self._jobs.values() if item.state is JobState.AWAITING_RESULT), None)
            if job is None:
                return False
            self._finish_locked(job, JobState.FAILED, code="recognition_failed", message=message)
            return True

    def get(self, job_id: str, *, principal_id: str) -> dict[str, Any]:
        with self._lock:
            self._purge_locked()
            job = self._owned_job_locked(job_id, principal_id)
            return job.snapshot()

    def wait(self, job_id: str, *, principal_id: str, timeout: float | None) -> dict[str, Any]:
        with self._lock:
            job = self._owned_job_locked(job_id, principal_id)
            event = job.event
        event.wait(timeout)
        return self.get(job_id, principal_id=principal_id)

    def cancel(self, job_id: str, *, principal_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._owned_job_locked(job_id, principal_id)
            if job.state in (JobState.COMPLETED, JobState.FAILED, JobState.CANCELED):
                return job.snapshot()
            job.cancel_requested = True
            if job.state in (JobState.QUEUED, JobState.AWAITING_RESULT):
                if job.state is JobState.QUEUED:
                    self._release_queue_slot_locked()
                self._finish_locked(job, JobState.CANCELED, code="canceled", message="识别任务已取消。")
            return job.snapshot()

    def run_external_operation(self, callback: Callable[[], Any]) -> Any:
        """Serialize a trusted desktop external-model operation with API calls."""
        operation = _ExternalOperation(callback)
        with self._lock:
            if self._stopping:
                raise RuntimeError("识别服务正在停止。")
            if self._queued_count >= self._limits.max_queued_jobs:
                raise AutomationApiError(503, "queue_full", "识别队列已满。")
            self._queued_count += 1
            try:
                self._queues["external"].put_nowait(operation)
            except queue.Full as exc:
                self._queued_count -= 1
                raise AutomationApiError(503, "queue_full", "识别队列已满。") from exc
        operation.event.wait()
        if operation.error is not None:
            raise operation.error
        return operation.result

    def stop(self, *, wait: bool = True) -> None:
        with self._lock:
            if self._stopping:
                return
            self._stopping = True
            for job in self._jobs.values():
                if job.state in (JobState.QUEUED, JobState.AWAITING_RESULT):
                    job.cancel_requested = True
                    if job.state is JobState.QUEUED:
                        self._release_queue_slot_locked()
                    self._finish_locked(job, JobState.CANCELED, code="canceled", message="识别任务已取消。")
        for backend, worker in self._workers.items():
            if worker.is_alive():
                self._queues[backend].put(_STOP)
        if wait:
            for worker in self._workers.values():
                if worker.is_alive():
                    worker.join()
        with self._lock:
            self._jobs.clear()
            self._queued_count = 0
            self._active_image_memory = 0

    def _owned_job_locked(self, job_id: str, principal_id: str) -> RecognitionJob:
        job = self._jobs.get(job_id)
        if job is not None and job.principal_id == principal_id:
            return job
        if job_id in self._expired_ids:
            raise AutomationApiError(410, "job_expired", "识别任务已过期。")
        raise AutomationApiError(404, "job_not_found", "未找到识别任务。")

    def _worker_main(self, backend: str) -> None:
        work_queue = self._queues[backend]
        while True:
            value = work_queue.get()
            if value is _STOP:
                return
            if isinstance(value, _ExternalOperation):
                with self._lock:
                    self._queued_count = max(0, self._queued_count - 1)
                    stopping = self._stopping
                if stopping:
                    value.error = RuntimeError("识别服务正在停止。")
                    value.event.set()
                    continue
                try:
                    value.result = value.callback()
                except BaseException as exc:
                    value.error = exc
                finally:
                    value.event.set()
                continue
            job_id = str(value)
            with self._lock:
                job = self._jobs.get(job_id)
                if job is None or job.state is not JobState.QUEUED or job.backend != backend:
                    continue
                self._release_queue_slot_locked()
                if self._expired(job):
                    self._finish_locked(job, JobState.FAILED, code="timeout", message="识别任务已超时。")
                    continue
                job.state = JobState.RUNNING
                job.started_at = utc_now_iso()
                for item in job.items:
                    if item.state == "queued":
                        item.state = "running"
            self._run_job(job)

    def _run_job(self, job: RecognitionJob) -> None:
        for index, item_input in enumerate(job.images):
            with self._lock:
                if job.cancel_requested:
                    break
                if self._expired(job):
                    self._finish_locked(job, JobState.FAILED, code="timeout", message="识别任务已超时。")
                    return
            started = self._clock()
            try:
                text = self._predict(item_input.image, job).strip()
                if not text:
                    raise RuntimeError("识别结果为空。")
            except Exception as exc:
                with self._lock:
                    item = job.items[index]
                    item.state = "failed"
                    item.elapsed_ms = round((self._clock() - started) * 1000)
                    code, message = self._safe_execution_error(job.backend, exc)
                    item.error = {"code": code, "message": message}
                continue
            with self._lock:
                item = job.items[index]
                item.state = "completed"
                item.text = text
                item.elapsed_ms = round((self._clock() - started) * 1000)

        with self._lock:
            if job.cancel_requested:
                self._finish_locked(job, JobState.CANCELED, code="canceled", message="识别任务已取消。")
            elif self._expired(job):
                self._finish_locked(job, JobState.FAILED, code="timeout", message="识别任务已超时。")
            elif job.items and all(item.state == "failed" for item in job.items):
                first_error = job.items[0].error or {
                    "code": "internal_error",
                    "message": "识别失败。",
                }
                self._finish_locked(
                    job,
                    JobState.FAILED,
                    code=first_error["code"],
                    message=first_error["message"],
                )
            else:
                self._finish_locked(job, JobState.COMPLETED)

    def _predict(self, image: Any, job: RecognitionJob) -> str:
        if job.backend == "external":
            return self._external_executor.predict(image, job.backend_config)
        image = optimize_mathcraft_input_image(image)
        predictor = self._predictor
        if callable(predictor) and not hasattr(predictor, "predict_result"):
            return str(predictor(image, job.mode) or "")
        model_name = _MODE_TO_MODEL[job.mode]
        result = predictor.predict_result(image, model_name=model_name)
        return str(result.get("text", "") or "")

    @staticmethod
    def _safe_execution_error(backend: str, exc: Exception) -> tuple[str, str]:
        if isinstance(exc, AutomationApiError):
            return exc.code, exc.message
        if backend == "external":
            name = type(exc).__name__
            if name == "ExternalModelConfigError":
                return "backend_unavailable", "外部模型尚未配置。"
            if "不支持图片" in str(exc) or "unsupported image" in str(exc).lower():
                return "backend_unsupported", "当前外部模型不支持图片输入。"
            if "Timeout" in name or "timeout" in str(exc).lower():
                return "upstream_timeout", "外部模型识别已超时。"
            return "upstream_error", "外部模型识别失败。"
        return "internal_error", "识别失败。"

    def _expired(self, job: RecognitionJob) -> bool:
        return self._clock() - job.created_monotonic >= job.timeout_seconds

    def _release_queue_slot_locked(self) -> None:
        self._queued_count = max(0, self._queued_count - 1)

    def _release_image_budget_locked(self, job: RecognitionJob) -> None:
        if not job.memory_reserved:
            return
        self._active_image_memory = max(0, self._active_image_memory - job.memory_bytes)
        job.memory_reserved = False

    def _finish_locked(
        self,
        job: RecognitionJob,
        state: JobState,
        *,
        code: str | None = None,
        message: str | None = None,
    ) -> None:
        job.state = state
        job.completed_at = utc_now_iso()
        job.completed_monotonic = self._clock()
        if code and message:
            job.error = {"code": code, "message": message}
        if code in {"timeout", "canceled"}:
            for item in job.items:
                item.text = None
                if item.state not in {"failed"}:
                    item.state = "canceled" if code == "canceled" else "failed"
                    item.error = {"code": code, "message": message or "识别任务已结束。"}
        elif state is JobState.FAILED:
            for item in job.items:
                if item.state not in {"completed", "failed"}:
                    item.state = "failed"
                    item.error = {
                        "code": code or "internal_error",
                        "message": message or "识别失败。",
                    }
        self._release_image_budget_locked(job)
        job.images.clear()
        job.backend_config = None
        job.event.set()
        self._purge_locked()

    def _purge_locked(self) -> None:
        now = self._clock()
        for job in self._jobs.values():
            if job.state is JobState.AWAITING_RESULT and self._expired(job):
                job.state = JobState.FAILED
                job.completed_at = utc_now_iso()
                job.completed_monotonic = now
                job.error = {"code": "timeout", "message": "识别任务已超时。"}
                for item in job.items:
                    item.state = "failed"
                    item.error = {"code": "timeout", "message": "识别任务已超时。"}
                job.backend_config = None
                job.event.set()
        ttl = self._limits.completed_job_ttl_seconds
        removable = [
            job_id
            for job_id, job in self._jobs.items()
            if job.completed_monotonic is not None and now - job.completed_monotonic >= ttl
        ]
        completed = [job_id for job_id, job in self._jobs.items() if job.completed_monotonic is not None]
        excess = max(0, len(completed) - self._limits.max_retained_jobs)
        removable.extend(completed[:excess])
        for job_id in dict.fromkeys(removable):
            self._jobs.pop(job_id, None)
            self._expired_ids[job_id] = now
        while len(self._expired_ids) > self._limits.max_retained_jobs:
            self._expired_ids.popitem(last=False)
