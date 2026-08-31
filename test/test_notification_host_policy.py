from __future__ import annotations

from types import SimpleNamespace

import ui.hotkey_controller as hotkey_module
import ui.predict_result_controller as result_module
from ui.model_runtime_controller import ModelRuntimeControllerMixin
from ui.predict_result_controller import PredictResultControllerMixin


def test_external_model_guidance_targets_settings_after_opening() -> None:
    events: list[tuple] = []

    class Settings:
        def isVisible(self) -> bool:
            return True

    class Harness(ModelRuntimeControllerMixin):
        settings_window = Settings()

        def set_model_status(self, text: str) -> None:
            events.append(("status", text))

        def open_settings(self) -> None:
            events.append(("open",))

        @staticmethod
        def _get_external_model_required_fields_hint() -> str:
            return "请填写模型名。"

        def show_action_status(self, text: str, **kwargs) -> None:
            events.append(("notice", text, kwargs["parent"]))

    harness = Harness()
    harness._open_external_model_settings_with_notice()

    assert [event[0] for event in events] == ["status", "open", "notice"]
    assert events[-1][2] is harness.settings_window


def test_hotkey_validation_error_targets_the_open_dialog(monkeypatch) -> None:
    notices: list[dict] = []
    monkeypatch.setattr(
        hotkey_module,
        "InfoBar",
        SimpleNamespace(error=lambda **kwargs: notices.append(kwargs)),
    )
    dialog = object()

    hotkey_module.HotkeyControllerMixin().update_hotkey("", dialog)

    assert notices and notices[0]["parent"] is dialog


def test_result_dialog_stays_open_when_history_write_fails(monkeypatch) -> None:
    monkeypatch.setattr(result_module.pyperclip, "copy", lambda _text: None)
    notices: list[tuple[str, object]] = []

    class Dialog:
        _predict_result_pinned = False
        _predict_result_mode = "mathcraft"

        def __init__(self) -> None:
            self.accepted = False

        def accept(self) -> None:
            self.accepted = True

    class Editor:
        @staticmethod
        def toPlainText() -> str:
            return "x^2"

    class Harness(PredictResultControllerMixin):
        def add_history_record(self, _text: str, *, content_type: str) -> None:
            raise OSError("history unavailable")

        def show_action_status(self, text: str, *, parent=None, **_kwargs) -> None:
            notices.append((text, parent))

    dialog = Dialog()
    Harness().accept_recognition_result(dialog, Editor())

    assert not dialog.accepted
    assert notices == [("写入历史失败：history unavailable", dialog)]
