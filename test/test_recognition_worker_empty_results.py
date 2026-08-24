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


def test_prediction_worker_routes_blank_formula_result_to_failure_signal() -> None:
    worker = PredictionWorker(_EmptyResultWrapper(), Image.new("RGB", (32, 16), "white"), "mathcraft")
    finished: list[str] = []
    failed: list[str] = []

    worker.finished.connect(finished.append)
    worker.failed.connect(failed.append)
    worker.run()

    assert finished == []
    assert failed == ["未识别到公式内容"]


def test_prediction_worker_routes_blank_text_result_to_failure_signal() -> None:
    worker = PredictionWorker(
        _TextEmptyResultWrapper(),
        Image.new("RGB", (32, 16), "white"),
        "mathcraft_text",
    )
    finished: list[str] = []
    failed: list[str] = []

    worker.finished.connect(finished.append)
    worker.failed.connect(failed.append)
    worker.run()

    assert finished == []
    assert failed == ["未识别到文本内容"]


def test_prediction_worker_routes_blank_mixed_result_to_failure_signal() -> None:
    worker = PredictionWorker(
        _MixedEmptyResultWrapper(),
        Image.new("RGB", (32, 16), "white"),
        "mathcraft_mixed",
    )
    finished: list[str] = []
    failed: list[str] = []

    worker.finished.connect(finished.append)
    worker.failed.connect(failed.append)
    worker.run()

    assert finished == []
    assert failed == ["未检测到可识别内容"]


@pytest.mark.parametrize(
    ("wrapper", "model_name", "expected"),
    (
        (_EmptyResultWrapper(), "mathcraft", "未识别到公式内容"),
        (_TextEmptyResultWrapper(), "mathcraft_text", "未识别到文本内容"),
        (_MixedEmptyResultWrapper(), "mathcraft_mixed", "未检测到可识别内容"),
    ),
)
def test_coordinator_preserves_empty_result_classification(wrapper, model_name: str, expected: str) -> None:
    coordinator = RecognitionJobCoordinator(wrapper)
    worker = PredictionWorker(
        wrapper,
        Image.new("RGB", (32, 16), "white"),
        model_name,
        coordinator,
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
