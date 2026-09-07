from __future__ import annotations


import ui.settings_environment_mixin as environment_module


def test_unready_environment_terminal_reports_through_infobar() -> None:
    messages: list[tuple[str, str, str]] = []

    class Harness(environment_module.SettingsEnvironmentMixin):
        @staticmethod
        def _resolve_dynamic_main_pyexe() -> str:
            return ""

        def _show_info(self, title: str, content: str, level: str = "info") -> None:
            messages.append((title, content, level))

    Harness()._open_environment_terminal()

    assert len(messages) == 1
    assert messages[0][0] == "环境未就绪"
    assert messages[0][2] == "warning"
