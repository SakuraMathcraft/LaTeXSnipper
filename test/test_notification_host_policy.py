from __future__ import annotations

from types import SimpleNamespace

import ui.controllers.hotkey as hotkey_module
import ui.controllers.model_runtime as runtime_module
import ui.controllers.predict_result as result_module
from ui.controllers.model_runtime import ModelRuntimeController
from ui.controllers.predict_result import RecognitionResultController


def test_cancelled_warmup_releases_callbacks_without_failure_notice(monkeypatch):
    statuses, failures = [], []

    def unexpected_warning(**kwargs):
        raise AssertionError("Unexpected warning")

    monkeypatch.setattr(runtime_module.InfoBar, "warning", unexpected_warning)
    controller = SimpleNamespace(
        _model_warmup_cancelled=False,
        _model_warmup_in_progress=True,
        _model_warmup_callbacks=[(None, failures.append)],
        current_model="mathcraft_mixed",
        status_changed=SimpleNamespace(emit=statuses.append),
    )
    ModelRuntimeController._apply_model_warmup_result(
        controller,
        {
            "ok": False,
            "cancelled": True,
            "preferred": "mathcraft_mixed",
            "announce_success": True,
        },
    )
    assert not controller._model_warmup_in_progress
    assert controller._model_warmup_callbacks == []
    assert failures == [runtime_module.tr(runtime_module.CANCELED_WORKER_MESSAGE)]
    assert statuses == [runtime_module.tr("待识别时加载")]


def test_external_model_guidance_targets_settings_after_opening() -> None:
    events = []
    settings = SimpleNamespace(isVisible=lambda: True)
    controller = SimpleNamespace(
        status_changed=SimpleNamespace(
            emit=lambda text: events.append(("status", text))
        ),
        settings_requested=SimpleNamespace(emit=lambda: events.append(("open",))),
        notification_parent=lambda: settings,
        _get_external_model_required_fields_hint=lambda: "请填写模型名。",
        notice=lambda text, **kwargs: events.append(("notice", text, kwargs["parent"])),
    )
    ModelRuntimeController.show_external_configuration(controller)
    assert [event[0] for event in events] == ["status", "open", "notice"]
    assert events[-1][2] is settings


def test_hotkey_validation_error_targets_the_open_dialog(monkeypatch) -> None:
    notices: list[dict] = []
    monkeypatch.setattr(
        hotkey_module,
        "InfoBar",
        SimpleNamespace(error=lambda **kwargs: notices.append(kwargs)),
    )
    dialog = object()
    hotkey_module.HotkeyController.update_hotkey(SimpleNamespace(), "", dialog)
    assert notices and notices[0]["parent"] is dialog


def test_result_dialog_stays_open_when_history_write_fails(monkeypatch) -> None:
    monkeypatch.setattr(result_module.pyperclip, "copy", lambda text: None)
    notices = []

    def fail_history(*args, **kwargs):
        raise OSError("history unavailable")

    dialog = SimpleNamespace(
        _predict_result_pinned=False, _predict_result_mode="mathcraft", accepted=False
    )
    controller = SimpleNamespace(
        history=SimpleNamespace(add_history_record=fail_history),
        status=SimpleNamespace(
            show_action_status=lambda text, **kwargs: notices.append(
                (text, kwargs["parent"])
            )
        ),
    )
    RecognitionResultController.accept_recognition_result(
        controller, dialog, SimpleNamespace(toPlainText=lambda: "x^2")
    )
    assert not dialog.accepted
    assert notices == [("写入历史失败：history unavailable", dialog)]
