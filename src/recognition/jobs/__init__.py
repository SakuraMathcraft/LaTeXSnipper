"""Recognition job domain and single-worker coordinator."""

from .coordinator import RecognitionJobCoordinator
from .contracts import DEFAULT_RECOGNITION_LIMITS, RecognitionJobError, RecognitionLimits
from .executors import ExternalRecognitionExecutor
from .models import JobSource, JobState, RecognitionItemInput

__all__ = [
    "ExternalRecognitionExecutor",
    "DEFAULT_RECOGNITION_LIMITS",
    "JobSource",
    "JobState",
    "RecognitionItemInput",
    "RecognitionJobError",
    "RecognitionJobCoordinator",
    "RecognitionLimits",
]
