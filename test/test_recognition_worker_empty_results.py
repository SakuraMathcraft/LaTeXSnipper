from __future__ import annotations

from PIL import Image

from workers.recognition_workers import PredictionWorker


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
