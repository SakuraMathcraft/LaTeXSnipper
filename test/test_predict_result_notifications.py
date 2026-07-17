from __future__ import annotations

from ui.predict_result_controller import (
    RECOGNITION_FAILURE_TRAY_COOLDOWN_SECONDS,
    PredictResultControllerMixin,
)


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
