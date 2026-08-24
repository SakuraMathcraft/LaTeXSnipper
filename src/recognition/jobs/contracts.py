"""Transport-independent recognition job contracts."""

from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class RecognitionLimits:
    max_batch_items: int = 16
    max_queued_jobs: int = 32
    max_queued_image_bytes: int = 256 * 1024 * 1024
    completed_job_ttl_seconds: float = 15 * 60.0
    max_retained_jobs: int = 256


DEFAULT_RECOGNITION_LIMITS = RecognitionLimits()


class RecognitionJobError(Exception):
    """A frontend-safe job error with a stable, transport-neutral code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)
        self.message = str(message)
