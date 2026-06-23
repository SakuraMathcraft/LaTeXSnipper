from __future__ import annotations

from pathlib import Path

from ui.predict_result_controller import (
    RECOGNITION_FAILURE_TRAY_COOLDOWN_SECONDS,
    PredictResultControllerMixin,
)


ROOT = Path(__file__).resolve().parents[1]


class _DummyPredictResultController(PredictResultControllerMixin):
    pass


def test_recognition_failure_tray_notification_is_rate_limited() -> None:
    controller = _DummyPredictResultController()

    assert controller._should_show_recognition_failure_tray_notification(100.0)
    assert not controller._should_show_recognition_failure_tray_notification(
        100.0 + RECOGNITION_FAILURE_TRAY_COOLDOWN_SECONDS - 0.1
    )
    assert controller._should_show_recognition_failure_tray_notification(
        100.0 + RECOGNITION_FAILURE_TRAY_COOLDOWN_SECONDS
    )


def test_recognition_success_does_not_use_hidden_tray_notification_setting() -> None:
    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            ROOT / "src" / "ui" / "predict_result_controller.py",
            ROOT / "src" / "ui" / "main_window_setup.py",
        )
    )

    assert "show_capture_success_toast" not in sources
    assert "_last_capture_toast_ts" not in sources
