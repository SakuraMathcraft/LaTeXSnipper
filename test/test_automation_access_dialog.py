from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from ui.automation_access_dialog import AutomationAccessDialog

_APP = QApplication.instance() or QApplication([])


class _Config:
    def __init__(self, values: dict[str, object] | None = None) -> None:
        self._values = values or {}

    def get(self, key: str, default=None):
        return self._values.get(key, default)


class _Window:
    def __init__(self, values: dict[str, object] | None = None) -> None:
        self.cfg = _Config(values)
        self.automation_api = self
        self.updates: list[dict[str, object]] = []

    @staticmethod
    def automation_api_status_text() -> str:
        return "Automation API 已关闭"

    def update_automation_api_settings_async(self, values, callback) -> None:
        self.updates.append(values)
        callback(True, "配置已保存")


def test_local_access_hides_the_complete_remote_card() -> None:
    dialog = AutomationAccessDialog(_Window())

    assert dialog.remote_card.isHidden()

    dialog.scope.setCurrentIndex(dialog.scope.findData("remote"))
    assert not dialog.remote_card.isHidden()
    assert dialog.cert_row.isHidden()
    assert dialog.private_key_row.isHidden()

    dialog.security.setCurrentIndex(dialog.security.findData("https"))
    assert not dialog.cert_row.isHidden()
    assert not dialog.private_key_row.isHidden()
    dialog.close()


def test_remote_access_requires_explicit_risk_acknowledgement() -> None:
    window = _Window()
    dialog = AutomationAccessDialog(window)
    messages: list[tuple[str, str, str]] = []
    dialog._show_info = lambda title, content, level="info": messages.append(
        (title, content, level)
    )
    dialog.scope.setCurrentIndex(dialog.scope.findData("remote"))

    dialog._save()

    assert window.updates == []
    assert messages == [
        (
            "需要确认远程访问风险",
            "请确认连接方式安全，并勾选远程访问确认项。",
            "warning",
        )
    ]
    dialog.close()


def test_local_save_reports_success_without_a_message_box() -> None:
    window = _Window()
    dialog = AutomationAccessDialog(window)
    messages: list[tuple[str, str, str]] = []
    dialog._show_info = lambda title, content, level="info": messages.append(
        (title, content, level)
    )

    dialog._save()

    assert len(window.updates) == 1
    assert messages == [("自动化接口", "配置已保存", "success")]
    dialog.close()
