"""Behavioral coverage for the shared native onboarding flow."""

from PyQt6.QtCore import QPoint, pyqtSignal, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
import pytest

from ui.onboarding_controller import AUTO_SHOW_KEY, OnboardingController


class Config:
    def __init__(self):
        self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value


class Host(QMainWindow):
    modelStatusChanged = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.cfg = Config()
        self._model_warmup_in_progress = False
        self.setCentralWidget(QWidget())
        layout = QVBoxLayout(self.centralWidget())
        for name in (
            "capture_button",
            "latex_editor",
            "preview_view",
            "export_btn",
            "change_key_button",
            "status_label",
            "onboarding_button",
        ):
            widget = QPushButton(name)
            setattr(self, name, widget)
            layout.addWidget(widget)
        self.resize(1180, 720)
        self.onboarding = OnboardingController(self)

    def set_shortcut(self):
        self.shortcut_window = QDialog(self)
        self.shortcut_window.show()


@pytest.fixture(scope="session")
def qt_app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def host(qt_app):
    app = qt_app
    window = Host()
    window.show()
    app.processEvents()
    yield window
    window.close()
    window.deleteLater()
    app.processEvents()


def test_complete_and_manual_replay_preserve_preference(host):
    tour = host.onboarding
    tour.start_automatically()
    for _ in range(6):
        tour.advance()
    assert not tour.active
    assert host.cfg.get(AUTO_SHOW_KEY) is False
    tour.start_automatically()
    assert not tour.active
    tour.start()
    tour.finish()
    assert host.cfg.get(AUTO_SHOW_KEY) is False


@pytest.mark.parametrize("action", ["skip", "close_button", "escape"])
def test_automatic_exit_disables_future_tours(host, action):
    tour = host.onboarding
    tour.start_automatically()
    tour.advance()
    if action == "escape":
        QTest.keyClick(tour.surface, Qt.Key.Key_Escape)
    else:
        getattr(tour.surface, action).click()
    assert tour.active
    assert host.cfg.get(AUTO_SHOW_KEY, True) is True
    tour.surface.back.click()
    assert tour.index == 1
    tour.request_exit()
    tour.surface.next.click()
    assert not tour.active
    assert host.cfg.get(AUTO_SHOW_KEY) is False


@pytest.mark.parametrize("preference", [True, False])
def test_manual_exit_and_application_close_preserve_preference(host, preference):
    host.cfg.set(AUTO_SHOW_KEY, preference)
    tour = host.onboarding
    tour.start()
    tour.finish()
    assert host.cfg.get(AUTO_SHOW_KEY) is preference
    tour.start(automatic=True)
    host.close()
    assert not tour.active
    assert host.cfg.get(AUTO_SHOW_KEY) is preference


def test_model_busy_only_affects_preparation_ring(host):
    tour = host.onboarding
    tour.start()
    for _ in range(3):
        tour.advance()
    host._model_warmup_in_progress = True
    host.modelStatusChanged.emit()
    assert tour.surface.ring.isVisible()
    host._model_warmup_in_progress = False
    host.modelStatusChanged.emit()
    assert not tour.surface.ring.isVisible()
    tour.advance()
    tour.advance()
    title = tour.surface.title.text()
    host._model_warmup_in_progress = True
    host.modelStatusChanged.emit()
    assert tour.surface.title.text() == title
    assert not tour.surface.ring.isVisible()
    tour.advance()
    assert host._model_warmup_in_progress


def test_shortcut_pause_resume_and_single_instance(host):
    tour = host.onboarding
    tour.start()
    tour.advance()
    tour.advance()
    tour.action("shortcut")
    assert not tour.surface.isVisible()
    tour.start()
    assert tour.index == 2
    host.cfg.set("hotkey", "Ctrl+Shift+K")
    host.shortcut_window.close()
    QApplication.processEvents()
    assert tour.surface.isVisible()
    assert tour.surface.detail.text() == "Ctrl+Shift+K"


def test_resize_keeps_card_inside_surface(host):
    tour = host.onboarding
    tour.start()
    for _ in range(6):
        host.resize(980, 680)
        QApplication.processEvents()
        assert tour.surface.rect().contains(tour.surface.card.geometry())
        tour.advance()


def test_tab_stays_inside_card_and_closed_tour_does_not_reopen(host):
    tour = host.onboarding
    tour.start()
    for _ in range(16):
        QTest.keyClick(QApplication.focusWidget(), Qt.Key.Key_Tab)
        assert tour.surface.card.isAncestorOf(QApplication.focusWidget())
    tour.finish()
    tour.render()
    assert not tour.surface.isVisible()


@pytest.mark.parametrize("origin", [(140, 90), (380, 220)])
def test_spotlights_align_with_nested_widgets_after_move_and_resize(host, origin):
    panel = QWidget(host.centralWidget())
    panel.setGeometry(35, 60, 700, 450)
    panel.show()
    target = host.capture_button
    target.setParent(panel)
    target.setGeometry(25, 30, 200, 40)
    target.show()
    host.move(*origin)
    host.resize(1250, 780)
    host.onboarding.start()
    host.onboarding.advance()
    QApplication.processEvents()
    surface = host.onboarding.surface
    for widget, rect in zip(surface.targets, surface.target_rects()):
        actual = surface.mapToGlobal(rect.topLeft().toPoint() + QPoint(5, 5))
        assert actual == widget.mapToGlobal(QPoint())
        assert rect.width() == widget.width() + 10
        assert rect.height() == widget.height() + 10
    assert host.preview_view in surface.targets
    host.onboarding.advance()
    rect = surface.target_rects()[0]
    assert surface.mapToGlobal(
        rect.topLeft().toPoint() + QPoint(5, 5)
    ) == host.change_key_button.mapToGlobal(QPoint())


@pytest.mark.parametrize(
    "language,page,fragment",
    [
        ("zh_CN", "README.zh-CN.md", "支持本项目"),
        ("en_US", "readme.md", "support-the-project"),
    ],
)
def test_combined_support_opens_readme_for_current_ui_language(
    host, monkeypatch, language, page, fragment
):
    import ui.onboarding_controller as controller

    opened = []
    monkeypatch.setattr(controller, "current_ui_language", lambda: language)
    monkeypatch.setattr(
        controller.QDesktopServices, "openUrl", lambda url: opened.append(url) or True
    )
    tour = host.onboarding
    tour.start()
    for _ in range(4):
        tour.advance()
    assert tour.surface.actions.count() == 3
    tour.surface.actions.itemAt(2).widget().click()
    assert len(opened) == 1
    assert opened[0].path().endswith("/" + page)
    assert opened[0].fragment() == fragment
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    assert page in {entry.name for entry in root.iterdir() if entry.is_file()}


@pytest.mark.parametrize("with_auxiliary", [False, True])
def test_window_destruction_does_not_access_deleted_qt_objects(
    qt_app, monkeypatch, with_auxiliary
):
    import sys
    from PyQt6 import sip
    from PyQt6.QtCore import QEvent

    errors = []
    monkeypatch.setattr(sys, "excepthook", lambda *error: errors.append(error))
    window = Host()
    window.show()
    tour = window.onboarding
    tour.start()
    if with_auxiliary:
        tour.action("shortcut")
        window.shortcut_window.close()
    sip.delete(window)
    QApplication.processEvents()
    assert not errors
    assert tour.eventFilter(None, QEvent(QEvent.Type.ChildRemoved)) is False
    tour.render()
    tour.refresh_busy()
