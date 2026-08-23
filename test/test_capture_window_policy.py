from __future__ import annotations

import types

from PyQt6.QtCore import Qt

import capture.capture_controller as capture_controller
from capture.capture_controller import CaptureControllerMixin


class _Window:
    def __init__(self, *, visible: bool = True, minimized: bool = False, pinned: bool = False):
        self._visible = visible
        self._state = (
            Qt.WindowState.WindowMinimized if minimized else Qt.WindowState.WindowNoState
        )
        self._predict_result_pinned = pinned
        self.hidden = 0
        self.minimized = 0

    def isVisible(self) -> bool:
        return self._visible

    def isMinimized(self) -> bool:
        return bool(self._state & Qt.WindowState.WindowMinimized)

    def hide(self) -> None:
        self._visible = False
        self.hidden += 1

    def showMinimized(self) -> None:
        self._visible = True
        self._state |= Qt.WindowState.WindowMinimized
        self.minimized += 1

    def windowState(self):
        return self._state

    def setWindowState(self, state) -> None:
        self._state = state


def _install_app(monkeypatch, windows: list[_Window]) -> None:
    app = types.SimpleNamespace(topLevelWidgets=lambda: windows)
    monkeypatch.setattr(
        capture_controller,
        "QApplication",
        types.SimpleNamespace(instance=lambda: app),
    )


def test_capture_minimizes_only_main_window_and_hides_auxiliary_windows(monkeypatch) -> None:
    main = _Window()
    settings = _Window()
    stale_minimized_dialog = _Window(visible=False, minimized=True)
    _install_app(monkeypatch, [settings, main, stale_minimized_dialog])

    changed = CaptureControllerMixin._prepare_windows_for_capture(main)

    assert changed
    assert main.minimized == 1
    assert settings.hidden == 1 and not settings.isMinimized()
    assert not stale_minimized_dialog.isMinimized()


def test_capture_shortcut_keeps_only_pinned_result_visible(monkeypatch) -> None:
    main = _Window()
    pinned_result = _Window(pinned=True)
    settings = _Window()
    _install_app(monkeypatch, [main, pinned_result, settings])

    CaptureControllerMixin._prepare_windows_for_capture(main, preserve_pinned_result=True)

    assert main.isMinimized()
    assert pinned_result.isVisible() and not pinned_result.isMinimized()
    assert not settings.isVisible() and not settings.isMinimized()
