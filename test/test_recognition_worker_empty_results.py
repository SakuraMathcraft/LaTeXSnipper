from __future__ import annotations

import pytest
from PIL import Image

from recognition.jobs import RecognitionJobCoordinator
from recognition.workers import PredictionWorker


class _EmptyResultWrapper:
    def predict_result(self, _image, model_name: str = "mathcraft"):
        return {
            "text": "",
            "score": 0.0,
            "mode": "formula",
            "model": model_name,
            "empty_reason": "empty_image",
        }


class _MixedEmptyResultWrapper:
    def predict_result(self, _image, model_name: str = "mathcraft_mixed"):
        return {
            "text": "",
            "mode": "mixed",
            "model": model_name,
            "empty_reason": "empty_image",
        }


class _TextEmptyResultWrapper:
    def predict_result(self, _image, model_name: str = "mathcraft_text"):
        return {
            "text": "",
            "mode": "text",
            "model": model_name,
            "empty_reason": "empty_image",
        }


@pytest.mark.parametrize(
    ("wrapper", "model_name", "expected"),
    (
        (_EmptyResultWrapper(), "mathcraft", "未识别到公式内容"),
        (_TextEmptyResultWrapper(), "mathcraft_text", "未识别到文本内容"),
        (_MixedEmptyResultWrapper(), "mathcraft_mixed", "未检测到可识别内容"),
    ),
)
def test_coordinator_preserves_empty_result_classification(
    wrapper, model_name: str, expected: str
) -> None:
    coordinator = RecognitionJobCoordinator(wrapper)
    worker = PredictionWorker(
        coordinator,
        Image.new("RGB", (32, 16), "white"),
        model_name,
    )
    finished: list[str] = []
    failed: list[str] = []
    worker.finished.connect(finished.append)
    worker.failed.connect(failed.append)
    try:
        worker.run()
    finally:
        coordinator.stop()

    assert finished == []
    assert failed == [expected]


def test_cancel_during_submission_is_delivered_before_wait():
    from types import SimpleNamespace

    from recognition.error_messages import CANCELED_WORKER_MESSAGE

    canceled = []
    finished = []
    failed = []

    def submit(*args, **kwargs):
        worker.cancel()
        return {"id": "job-1"}

    def wait(*args, **kwargs):
        assert canceled == [("job-1", "desktop-ui")]
        return {"state": "canceled"}

    coordinator = SimpleNamespace(
        submit=submit,
        cancel=lambda job_id, *, principal_id: canceled.append((job_id, principal_id)),
        wait=wait,
    )
    worker = PredictionWorker(
        coordinator, Image.new("RGB", (32, 16), "white"), "mathcraft"
    )
    worker.finished.connect(finished.append)
    worker.failed.connect(failed.append)
    worker.run()

    assert finished == []
    assert failed == [CANCELED_WORKER_MESSAGE]
