from __future__ import annotations

import os

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QLabel
from qfluentwidgets import PushButton

from editor.source_editor import SourceEditor
from handwriting import result_panel
from handwriting.canvas_panel import HandwritingCanvasPanel
from handwriting.canvas_viewport import CanvasViewport
from handwriting.tools import HandwritingTool
from localization.manager import translate as tr

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("wheel_target", ["canvas", "viewport"])
def test_ctrl_wheel_keeps_the_canvas_point_under_the_pointer(app, wheel_target):
    view = CanvasViewport()
    try:
        view.resize(450, 350)
        view.show()
        app.processEvents()
        viewport = view.viewport()
        hbar = view.horizontalScrollBar()
        vbar = view.verticalScrollBar()
        hbar.setValue(300)
        vbar.setValue(200)
        pointer = QPoint(120, 90)
        scene_at_pointer = QPointF(420, 290)
        receiver = view.canvas if wheel_target == "canvas" else viewport
        global_pos = viewport.mapToGlobal(pointer)
        event = QWheelEvent(
            QPointF(receiver.mapFromGlobal(global_pos)),
            QPointF(global_pos),
            QPoint(),
            QPoint(0, 120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.ControlModifier,
            Qt.ScrollPhase.ScrollUpdate,
            False,
        )

        app.sendEvent(receiver, event)
        app.processEvents()
        app.processEvents()

        zoom = view.canvas.zoom_factor()
        assert event.isAccepted()
        assert zoom > 1.0
        assert (hbar.value() + pointer.x()) / zoom == pytest.approx(
            scene_at_pointer.x(), abs=1.0
        )
        assert (vbar.value() + pointer.y()) / zoom == pytest.approx(
            scene_at_pointer.y(), abs=1.0
        )
    finally:
        view.close()


def test_right_drag_pans_without_creating_ink(app):
    view = CanvasViewport()
    try:
        view.resize(450, 350)
        view.show()
        app.processEvents()
        hbar = view.horizontalScrollBar()
        vbar = view.verticalScrollBar()
        hbar.setValue(300)
        vbar.setValue(200)
        start = view.canvas.mapFromGlobal(view.viewport().mapToGlobal(QPoint(120, 90)))
        end = start + QPoint(40, 30)

        QTest.mousePress(view.canvas, Qt.MouseButton.RightButton, pos=start)
        QTest.mouseMove(view.canvas, end)
        QTest.mouseRelease(view.canvas, Qt.MouseButton.RightButton, pos=end)

        assert (hbar.value(), vbar.value()) == (260, 170)
        assert view.canvas.store.is_empty()
    finally:
        view.close()


def test_toolbar_selects_tools_and_edits_canvas_history(app):
    panel = HandwritingCanvasPanel()
    try:
        buttons = {item.text(): item for item in panel.findChildren(PushButton)}
        QTest.mouseClick(buttons[tr("橡皮")], Qt.MouseButton.LeftButton)
        assert panel.canvas.current_tool is HandwritingTool.ERASE
        QTest.mouseClick(buttons[tr("圈选修正")], Qt.MouseButton.LeftButton)
        assert panel.canvas.current_tool is HandwritingTool.SELECT_CORRECT
        QTest.mouseClick(buttons[tr("书写")], Qt.MouseButton.LeftButton)
        QTest.mouseClick(panel.canvas, Qt.MouseButton.LeftButton, pos=QPoint(40, 40))
        assert not panel.canvas.store.is_empty()
        QTest.mouseClick(buttons[tr("撤销")], Qt.MouseButton.LeftButton)
        assert panel.canvas.store.is_empty()
        QTest.mouseClick(buttons[tr("重做")], Qt.MouseButton.LeftButton)
        assert not panel.canvas.store.is_empty()
        clear_requests = []
        panel.clear_requested.connect(lambda: clear_requests.append(True))
        QTest.mouseClick(buttons[tr("清空")], Qt.MouseButton.LeftButton)
        assert clear_requests == [True]
    finally:
        panel.close()


def test_handwriting_result_panel_updates_fallback_when_text_is_edited(
    app, monkeypatch
):
    monkeypatch.setattr(result_panel, "PreviewWebView", None)
    panel = result_panel.HandwritingResultPanel()
    try:
        editor = panel.findChild(SourceEditor)
        panel.text_changed.connect(lambda: panel.refresh_preview("latex"))
        panel.set_result(r"\[x^2\]", "latex")
        assert panel.text() == "x^2"

        editor.setPlainText(r"\[x^3\]")

        assert panel.text() == r"\[x^3\]"
        assert any(label.text().endswith("x^3") for label in panel.findChildren(QLabel))
        panel.set_result("", "latex")
        assert not panel.text()
        assert any(
            label.text().endswith("<empty>") for label in panel.findChildren(QLabel)
        )
    finally:
        panel.close()
