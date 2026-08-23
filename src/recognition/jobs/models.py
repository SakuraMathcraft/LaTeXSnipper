"""Thread-safe internal recognition job models."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from PIL import Image


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class JobState(StrEnum):
    AWAITING_RESULT = "awaiting_result"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class JobSource(StrEnum):
    UI = "ui"
    OFFICE = "office"
    LOCAL_API = "local_api"
    REMOTE_API = "remote_api"
    HANDWRITING = "handwriting"
    PDF = "pdf"


@dataclass(slots=True)
class RecognitionItemInput:
    image: Image.Image
    filename: str | None = None

    @property
    def memory_bytes(self) -> int:
        width, height = self.image.size
        return width * height * 3


@dataclass(slots=True)
class RecognitionItem:
    index: int
    filename: str | None
    state: str = "queued"
    text: str | None = None
    elapsed_ms: int | None = None
    error: dict[str, str] | None = None

    def snapshot(self) -> dict[str, Any]:
        result: dict[str, Any] = {"index": self.index, "state": self.state}
        if self.filename:
            result["filename"] = self.filename
        if self.text is not None:
            result["text"] = self.text
        if self.elapsed_ms is not None:
            result["elapsed_ms"] = self.elapsed_ms
        if self.error is not None:
            result["error"] = dict(self.error)
        return result


@dataclass(slots=True)
class RecognitionJob:
    id: str
    principal_id: str
    source: JobSource
    input_type: str
    backend: str
    mode: str
    timeout_seconds: float
    state: JobState
    images: list[RecognitionItemInput]
    items: list[RecognitionItem]
    backend_config: Any | None = None
    memory_reserved: bool = False
    created_at: str = field(default_factory=utc_now_iso)
    queued_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    created_monotonic: float = 0.0
    completed_monotonic: float | None = None
    cancel_requested: bool = False
    error: dict[str, str] | None = None
    event: threading.Event = field(default_factory=threading.Event)

    @property
    def memory_bytes(self) -> int:
        return sum(item.memory_bytes for item in self.images)

    def snapshot(self) -> dict[str, Any]:
        succeeded = sum(item.state == "completed" for item in self.items)
        failed = sum(item.state == "failed" for item in self.items)
        result: dict[str, Any] = {
            "id": self.id,
            "state": self.state.value,
            "backend": self.backend,
            "mode": self.mode,
            "created_at": self.created_at,
            "cancel_requested": self.cancel_requested,
            "summary": {"total": len(self.items), "succeeded": succeeded, "failed": failed},
            "items": [item.snapshot() for item in self.items],
        }
        if self.queued_at:
            result["queued_at"] = self.queued_at
        if self.started_at:
            result["started_at"] = self.started_at
        if self.completed_at:
            result["completed_at"] = self.completed_at
        if self.error:
            result["error"] = dict(self.error)
        return result
