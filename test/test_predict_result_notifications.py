from __future__ import annotations

from ui.controllers.predict_result import (
    RECOGNITION_FAILURE_TRAY_COOLDOWN_SECONDS,
    RecognitionResultController,
)


from types import SimpleNamespace
from functools import partial


def test_recognition_failure_tray_notification_is_rate_limited() -> None:
    controller = SimpleNamespace(_last_recognition_failure_toast_ts=0.0)
    controller._should_show_recognition_failure_tray_notification = partial(
        RecognitionResultController._should_show_recognition_failure_tray_notification,
        controller,
    )

    assert controller._should_show_recognition_failure_tray_notification(100.0)
    assert not controller._should_show_recognition_failure_tray_notification(
        100.0 + RECOGNITION_FAILURE_TRAY_COOLDOWN_SECONDS - 0.1
    )
    assert controller._should_show_recognition_failure_tray_notification(
        100.0 + RECOGNITION_FAILURE_TRAY_COOLDOWN_SECONDS
    )
