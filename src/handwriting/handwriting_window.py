from __future__ import annotations

import html
import math
import re
import time
from dataclasses import replace
from pathlib import Path

from PyQt6.QtCore import QEasingCurve, QEvent, QObject, QPoint, QPropertyAnimation, QRectF, QThread, QTimer, QUrl, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QMouseEvent, QWheelEvent
from PyQt6.QtWidgets import QApplication, QCheckBox, QDialog, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QScrollArea, QSplitter, QVBoxLayout, QWidget
from qfluentwidgets import FluentIcon, InfoBar, InfoBarPosition, PrimaryPushButton, PushButton, isDarkTheme

from backend.external_model import ExternalModelClient
from .ink_canvas import InkCanvas
from .recognizer import HandwritingRecognitionWorker
from .tools import HandwritingTool
from utils import resource_path

try:
    from PyQt6.QtWebEngineCore import QWebEngineSettings
except Exception:  # pragma: no cover
    QWebEngineSettings = None

from .document_preview_window import (
    HandwritingDocumentPreviewWindow as DocumentPreviewWindow,
    SlowZoomPlainTextEdit as PreviewPlainTextEdit,
    SlowZoomWebView as PreviewWebView,
)


class _HandwritingDocumentLayoutWorker(QObject):
    finished = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, config, image):
        super().__init__()
        self.config = config
        self.image = image

    def run(self) -> None:
        try:
            from .recognizer import qimage_to_pil

            pil_img = qimage_to_pil(self.image)
            result = ExternalModelClient(self.config).predict(pil_img)
            text = result.best_text("text").strip()
            if not text:
                self.failed.emit("自动排版结果为空")
                return
            self.finished.emit(text)
        except Exception as exc:
            self.failed.emit(str(exc))


class HandwritingWindow(QDialog):
    latexInserted = pyqtSignal(str)

    def __init__(self, model_wrapper, owner=None, parent=None):
        super().__init__(parent)
        self.model = model_wrapper
        self.owner = owner
        self._recognizing = False
        self._recognize_pending = False
        self._recognize_thread = None
        self._recognize_worker = None
        self._layout_thread = None
        self._layout_worker = None
        self._closing = False
        self._last_result = ""
        self._theme_is_dark_cached = None
        self._ui_ready = False
        self._soft_focus_target = None
        self._pending_zoom_anchor = None
        self._active_zoom_anchor = None
        self._last_busy_notice_ts = 0.0
        self._document_preview_window = None
        self._build_ui()
        self._wire_events()

    def _build_ui(self) -> None:
        self.setWindowTitle("手写识别")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )
        self.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, True)
        self.setWindowFlag(Qt.WindowType.WindowMinMaxButtonsHint, True)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self.resize(1120, 760)
        try:
            self.setWindowIcon(QIcon(resource_path("assets/icon.ico")))
        except Exception:
            pass

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        title_bar = QHBoxLayout()
        self.title_label = QLabel("手写识别")
        self.title_label.setObjectName("handwritingTitle")
        self.mode_hint_label = QLabel("当前圈选修正为自由圈选矢量裁剪并保留剩余笔段")
        self.mode_hint_label.setObjectName("handwritingModeHint")
        title_bar.addWidget(self.title_label)
        title_bar.addWidget(self.mode_hint_label)
        title_bar.addStretch(1)
        root.addLayout(title_bar)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.write_btn = PushButton(FluentIcon.PENCIL_INK, "书写")
        self.erase_btn = PushButton(FluentIcon.ERASE_TOOL, "橡皮")
        self.select_btn = PushButton(FluentIcon.CLIPPING_TOOL, "圈选修正")
        self.clear_btn = PushButton(FluentIcon.DELETE, "清空")
        self.undo_btn = PushButton(FluentIcon.CANCEL, "撤销")
        self.redo_btn = PushButton(FluentIcon.SYNC, "重做")
        for btn in (self.write_btn, self.erase_btn, self.select_btn, self.clear_btn, self.undo_btn, self.redo_btn):
            btn.setFixedHeight(34)
            toolbar.addWidget(btn)
        self._tool_button_base_styles = {}
        for btn in (self.write_btn, self.erase_btn, self.select_btn):
            self._tool_button_base_styles[btn] = btn.styleSheet()
        toolbar.addStretch(1)
        self.auto_focus_checkbox = QCheckBox("自动聚焦")
        self.auto_focus_checkbox.setChecked(False)
        toolbar.addWidget(self.auto_focus_checkbox)
        root.addLayout(toolbar)

        self.splitter = QSplitter()
        self.splitter.setObjectName("handwritingSplitter")
        self.splitter.setHandleWidth(14)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 10, 0)
        left_layout.setSpacing(6)
        self.canvas_title = QLabel("手写画布")
        self.canvas_title.setObjectName("handwritingSectionTitle")
        self.canvas_hint = QLabel("支持鼠标与触控笔。可先右键拖动画布定位，写完后自动回到内容重心。")
        self.canvas_hint.setObjectName("handwritingHint")
        left_layout.addWidget(self.canvas_title)
        left_layout.addWidget(self.canvas_hint)
        self.canvas = InkCanvas(self)
        self.canvas.set_auto_focus_enabled(False)
        self.canvas.installEventFilter(self)
        self.canvas_scroll = QScrollArea(self)
        self.canvas_scroll.setObjectName("handwritingCanvasScroll")
        self.canvas_scroll.setWidgetResizable(False)
        self.canvas_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.canvas_scroll.setWidget(self.canvas)
        self.canvas_scroll.viewport().installEventFilter(self)
        left_layout.addWidget(self.canvas_scroll, 1)
        self.splitter.addWidget(left)

        right = QWidget()
        right.setObjectName("handwritingRightPanel")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(12, 0, 0, 0)
        right_layout.setSpacing(12)
        self.result_section = QWidget(self)
        self.result_section.setObjectName("handwritingSubPanel")
        result_layout = QVBoxLayout(self.result_section)
        result_layout.setContentsMargins(14, 12, 14, 14)
        result_layout.setSpacing(10)
        result_header = QHBoxLayout()
        result_header.setContentsMargins(0, 0, 0, 0)
        result_header.setSpacing(8)
        self.result_title = QLabel("LaTeX 结果")
        self.result_title.setObjectName("handwritingSectionTitle")
        result_header.addWidget(self.result_title)
        result_header.addStretch(1)
        self.recognition_type_label = QLabel("")
        self.recognition_type_label.setObjectName("handwritingHint")
        result_header.addWidget(self.recognition_type_label)
        result_layout.addLayout(result_header)
        self.result_editor = PreviewPlainTextEdit(self)
        self.result_editor.setPlaceholderText("手写识别结果会显示在这里，可直接手动修正。")
        self.result_editor.setMinimumHeight(150)
        result_layout.addWidget(self.result_editor)
        right_layout.addWidget(self.result_section)
        self.preview_section = QWidget(self)
        self.preview_section.setObjectName("handwritingSubPanel")
        preview_layout = QVBoxLayout(self.preview_section)
        preview_layout.setContentsMargins(14, 12, 14, 14)
        preview_layout.setSpacing(10)
        self.preview_title = QLabel("实时预览")
        self.preview_title.setObjectName("handwritingSectionTitle")
        preview_layout.addWidget(self.preview_title)
        self.preview_view = None
        self.preview_fallback = None
        if PreviewWebView is not None:
            self.preview_view = PreviewWebView(self)
            self.preview_view.setObjectName("handwritingPreviewView")
            if QWebEngineSettings is not None:
                try:
                    settings = self.preview_view.settings()
                    settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
                    settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
                except Exception:
                    pass
            self.preview_view.setMinimumHeight(280)
            preview_layout.addWidget(self.preview_view, 1)
        else:
            self.preview_fallback = QLabel("WebEngine 不可用，无法显示公式预览。")
            self.preview_fallback.setWordWrap(True)
            preview_layout.addWidget(self.preview_fallback, 1)
        right_layout.addWidget(self.preview_section, 1)
        self.splitter.addWidget(right)
        self.splitter.setSizes([610, 470])
        root.addWidget(self.splitter, 1)

        bottom = QHBoxLayout()
        self.status_label = QLabel("就绪")
        self.status_label.setObjectName("handwritingStatus")
        bottom.addWidget(self.status_label)
        bottom.addStretch(1)
        self.copy_btn = PushButton(FluentIcon.COPY, "复制 LaTeX")
        layout_icon = getattr(FluentIcon, "HIGHLIGHT", None) or getattr(FluentIcon, "HIGHTLIGHT", FluentIcon.ALIGNMENT)
        self.layout_btn = PushButton(layout_icon, "自动排版")
        self.insert_btn = PrimaryPushButton(FluentIcon.ACCEPT, "插入")
        self.copy_btn.setFixedHeight(34)
        self.layout_btn.setFixedHeight(34)
        self.insert_btn.setFixedHeight(34)
        self._layout_btn_opacity = QGraphicsOpacityEffect(self.layout_btn)
        self._layout_btn_opacity.setOpacity(1.0)
        self.layout_btn.setGraphicsEffect(self._layout_btn_opacity)
        bottom.addWidget(self.copy_btn)
        bottom.addWidget(self.layout_btn)
        bottom.addWidget(self.insert_btn)
        root.addLayout(bottom)

        self.recognize_timer = QTimer(self)
        self.recognize_timer.setSingleShot(True)
        self.focus_timer = QTimer(self)
        self.focus_timer.setSingleShot(True)
        self.focus_timer.setInterval(1100)
        self._h_scroll_anim = QPropertyAnimation(self.canvas_scroll.horizontalScrollBar(), b"value", self)
        self._v_scroll_anim = QPropertyAnimation(self.canvas_scroll.verticalScrollBar(), b"value", self)
        for anim in (self._h_scroll_anim, self._v_scroll_anim):
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._set_active_tool(HandwritingTool.WRITE)
        self._refresh_recognition_context()
        self._refresh_preview_from_text("")
        self._ui_ready = True
        self.apply_theme_styles(force=True)
        self._apply_auto_focus_state(False)
        self._update_layout_button_state()
        QTimer.singleShot(0, self._sync_canvas_extent_to_viewport)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._ui_ready:
            QTimer.singleShot(0, self._sync_canvas_extent_to_viewport)

    def _sync_canvas_extent_to_viewport(self) -> None:
        viewport = self.canvas_scroll.viewport()
        frame_w = self.canvas_scroll.frameWidth() * 2
        zoom = max(0.01, self.canvas.zoom_factor())
        min_w = max(520, math.ceil((viewport.width() - frame_w - 2) / zoom))
        min_h = max(520, math.ceil((viewport.height() - frame_w - 2) / zoom))
        self.canvas.ensure_minimum_extent(min_w, min_h)
        self._update_canvas_viewport_rect()
        self._apply_pending_zoom_anchor()
        self._update_canvas_viewport_rect()

    def _update_canvas_viewport_rect(self) -> None:
        viewport = self.canvas_scroll.viewport()
        zoom = max(0.01, self.canvas.zoom_factor())
        top_left = self.canvas.mapFrom(viewport, QPoint(0, 0))
        bottom_right = self.canvas.mapFrom(viewport, QPoint(max(0, viewport.width() - 1), max(0, viewport.height() - 1)))
        left_px = max(0, min(top_left.x(), self.canvas.width()))
        top_px = max(0, min(top_left.y(), self.canvas.height()))
        right_px = max(0, min(bottom_right.x() + 1, self.canvas.width()))
        bottom_px = max(0, min(bottom_right.y() + 1, self.canvas.height()))
        width_px = max(0, right_px - left_px)
        height_px = max(0, bottom_px - top_px)
        rect = QRectF(
            left_px / zoom,
            top_px / zoom,
            width_px / zoom,
            height_px / zoom,
        )
        self.canvas.set_viewport_scene_rect(rect)

    def _wire_events(self) -> None:
        self.write_btn.clicked.connect(lambda: self._set_active_tool(HandwritingTool.WRITE))
        self.erase_btn.clicked.connect(lambda: self._set_active_tool(HandwritingTool.ERASE))
        self.select_btn.clicked.connect(lambda: self._set_active_tool(HandwritingTool.SELECT_CORRECT))
        self.clear_btn.clicked.connect(self._clear_all)
        self.undo_btn.clicked.connect(self._undo)
        self.redo_btn.clicked.connect(self._redo)
        self.copy_btn.clicked.connect(self._copy_result)
        self.layout_btn.clicked.connect(self._auto_layout_document)
        self.insert_btn.clicked.connect(self._insert_result)
        self.auto_focus_checkbox.toggled.connect(self._apply_auto_focus_state)
        self.canvas.contentChanged.connect(self._on_canvas_changed)
        self.canvas.viewportFollowRequested.connect(self._reposition_viewport_to_point)
        self.canvas.contentFocusRequested.connect(self._schedule_soft_focus)
        self.canvas.panRequested.connect(self._pan_canvas_view)
        self.canvas.canvasShifted.connect(self._on_canvas_shifted)
        self.canvas.zoomChanged.connect(lambda _z: QTimer.singleShot(0, self._sync_canvas_extent_to_viewport))
        self.canvas_scroll.horizontalScrollBar().valueChanged.connect(lambda _v: self._update_canvas_viewport_rect())
        self.canvas_scroll.verticalScrollBar().valueChanged.connect(lambda _v: self._update_canvas_viewport_rect())
        self.splitter.splitterMoved.connect(lambda *_args: QTimer.singleShot(0, self._sync_canvas_extent_to_viewport))
        self.result_editor.textChanged.connect(self._on_result_editor_changed)
        self.recognize_timer.timeout.connect(self._run_recognition)
        self.focus_timer.timeout.connect(self._apply_soft_focus)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._ui_ready:
            self._refresh_recognition_context()
            self.apply_theme_styles(force=True)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if self._ui_ready:
            self.apply_theme_styles()

    def eventFilter(self, obj, event):
        if (
            self._ui_ready
            and obj in (self.canvas, self.canvas_scroll.viewport())
            and event.type() == QEvent.Type.MouseButtonPress
            and isinstance(event, QMouseEvent)
            and event.button() == Qt.MouseButton.LeftButton
        ):
            self.focus_timer.stop()
            self._soft_focus_target = None
            self._h_scroll_anim.stop()
            self._v_scroll_anim.stop()
        if (
            self._ui_ready
            and obj in (self.canvas, self.canvas_scroll.viewport())
            and event.type() == QEvent.Type.Wheel
            and isinstance(event, QWheelEvent)
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self._zoom_canvas_at_pointer(obj, event)
            event.accept()
            return True
        if (
            self._ui_ready
            and obj is self.canvas_scroll.viewport()
            and event.type() == QEvent.Type.Resize
        ):
            QTimer.singleShot(0, self._sync_canvas_extent_to_viewport)
        return super().eventFilter(obj, event)

    def _zoom_canvas_at_pointer(self, source, event: QWheelEvent) -> bool:
        delta = event.angleDelta().y()
        if not delta:
            return False
        old_zoom = max(0.01, self.canvas.zoom_factor())
        viewport = self.canvas_scroll.viewport()
        hbar = self.canvas_scroll.horizontalScrollBar()
        vbar = self.canvas_scroll.verticalScrollBar()
        local_pos = event.position().toPoint()
        if source is self.canvas_scroll.viewport():
            viewport_pos = local_pos
        elif source is self.canvas:
            viewport_pos = self.canvas.mapTo(viewport, local_pos)
        else:
            viewport_pos = viewport.mapFromGlobal(event.globalPosition().toPoint())
        scene_x = (hbar.value() + viewport_pos.x()) / old_zoom
        scene_y = (vbar.value() + viewport_pos.y()) / old_zoom
        changed = self.canvas.zoom_in() if delta > 0 else self.canvas.zoom_out()
        if not changed:
            return False
        new_zoom = max(0.01, self.canvas.zoom_factor())
        if abs(new_zoom - old_zoom) < 1e-6:
            return False
        self._pending_zoom_anchor = (scene_x, scene_y, viewport_pos.x(), viewport_pos.y(), new_zoom)
        QTimer.singleShot(0, self._sync_canvas_extent_to_viewport)
        return True

    def _apply_pending_zoom_anchor(self) -> None:
        payload = self._pending_zoom_anchor
        self._pending_zoom_anchor = None
        if payload is None:
            return
        scene_x, scene_y, viewport_x, viewport_y, zoom = payload
        if abs(max(0.01, self.canvas.zoom_factor()) - zoom) > 1e-6:
            return
        self._active_zoom_anchor = (scene_x, scene_y, viewport_x, viewport_y, zoom)
        hbar = self.canvas_scroll.horizontalScrollBar()
        vbar = self.canvas_scroll.verticalScrollBar()
        target_x = int(round(scene_x * zoom - viewport_x))
        target_y = int(round(scene_y * zoom - viewport_y))
        hbar.setValue(max(hbar.minimum(), min(target_x, hbar.maximum())))
        vbar.setValue(max(vbar.minimum(), min(target_y, vbar.maximum())))
        self._update_canvas_viewport_rect()
        QTimer.singleShot(0, self._stabilize_zoom_anchor)

    def _stabilize_zoom_anchor(self) -> None:
        payload = self._active_zoom_anchor
        self._active_zoom_anchor = None
        if payload is None:
            return
        scene_x, scene_y, viewport_x, viewport_y, zoom = payload
        if abs(max(0.01, self.canvas.zoom_factor()) - zoom) > 1e-6:
            return
        hbar = self.canvas_scroll.horizontalScrollBar()
        vbar = self.canvas_scroll.verticalScrollBar()
        actual_scene_x = (hbar.value() + viewport_x) / zoom
        actual_scene_y = (vbar.value() + viewport_y) / zoom
        dx = int(round((scene_x - actual_scene_x) * zoom))
        dy = int(round((scene_y - actual_scene_y) * zoom))
        if not dx and not dy:
            return
        hbar.setValue(max(hbar.minimum(), min(hbar.value() - dx, hbar.maximum())))
        vbar.setValue(max(vbar.minimum(), min(vbar.value() - dy, vbar.maximum())))
        self._update_canvas_viewport_rect()

    def apply_theme_styles(self, force: bool = False) -> None:
        if not self._ui_ready:
            return
        dark = bool(isDarkTheme())
        if not force and self._theme_is_dark_cached is dark:
            return
        self._theme_is_dark_cached = dark
        self.canvas.set_dark_mode(dark)
        if dark:
            bg = "#171c24"
            text = "#eef2f7"
            subtext = "#a9b4c3"
            editor_bg = "#151a22"
            editor_border = "rgba(110, 130, 156, 0.45)"
            cb_text = "#c8d1dc"
            card_bg = "#151b23"
            subpanel_bg = "#121821"
            divider = "rgba(91, 111, 138, 0.24)"
        else:
            bg = "#f5f7fb"
            text = "#16202a"
            subtext = "#6b7787"
            editor_bg = "#ffffff"
            editor_border = "rgba(148, 163, 184, 0.55)"
            cb_text = "#334155"
            card_bg = "#ffffff"
            subpanel_bg = "#ffffff"
            divider = "rgba(148, 163, 184, 0.22)"
        self.setStyleSheet(
            f"""
            QDialog {{ background: {bg}; }}
            QLabel#handwritingTitle {{ color: {text}; font-size: 24px; font-weight: 600; padding-right: 10px; }}
            QLabel#handwritingModeHint {{ color: {subtext}; font-size: 12px; }}
            QLabel#handwritingSectionTitle {{ color: {text}; font-size: 14px; font-weight: 600; }}
            QLabel#handwritingHint {{ color: {subtext}; font-size: 12px; }}
            QLabel#handwritingStatus {{ color: {subtext}; font-size: 12px; padding-top: 4px; }}
            QCheckBox {{ color: {cb_text}; spacing: 8px; }}
            QPlainTextEdit {{
                background: {editor_bg};
                color: {text};
                border: 1px solid {editor_border};
                border-radius: 10px;
                padding: 8px;
                selection-background-color: {'#2f6fb3' if dark else '#0a84ff'};
                selection-color: #ffffff;
            }}
            QScrollArea#handwritingCanvasScroll {{
                background: {card_bg};
                border: 1px solid {editor_border};
                border-radius: 12px;
            }}
            QWidget#handwritingRightPanel {{
                background: transparent;
                border: none;
            }}
            QWidget#handwritingSubPanel {{
                background: {subpanel_bg};
                border: 1px solid {editor_border};
                border-radius: 14px;
            }}
            QSplitter#handwritingSplitter::handle {{
                background: transparent;
                width: 14px;
            }}
            QSplitter#handwritingSplitter::handle:horizontal {{
                image: none;
                border-left: 1px solid {divider};
                border-right: 1px solid transparent;
                margin-top: 12px;
                margin-bottom: 12px;
            }}
            """
        )
        self._refresh_preview_from_text(self.result_editor.toPlainText().strip())
        self._apply_tool_button_styles()

    def _on_canvas_shifted(self, dx: int, dy: int) -> None:
        hbar = self.canvas_scroll.horizontalScrollBar()
        vbar = self.canvas_scroll.verticalScrollBar()
        if dx:
            hbar.setValue(max(hbar.minimum(), min(hbar.value() + dx, hbar.maximum())))
        if dy:
            vbar.setValue(max(vbar.minimum(), min(vbar.value() + dy, vbar.maximum())))

    def _apply_tool_button_styles(self) -> None:
        dark = bool(self._theme_is_dark_cached)
        active_bg = "#4da3ff" if dark else "#4f8fe8"
        active_hover = "#6ab2ff" if dark else "#3f7fda"
        active_pressed = "#3c93ee" if dark else "#376fc0"
        active_border = "#9fd0ff" if dark else "#6aa3ef"
        active_fg = "#ffffff"
        inactive_bg = "transparent"
        inactive_hover = "rgba(255,255,255,0.06)" if dark else "rgba(15,23,42,0.04)"
        inactive_pressed = "rgba(255,255,255,0.1)" if dark else "rgba(15,23,42,0.08)"
        inactive_border = "#465162" if dark else "#d0d7de"
        inactive_fg = "#eef2f7" if dark else "#16202a"
        active_button = getattr(self, '_active_tool_button', None)
        for btn in (self.write_btn, self.erase_btn, self.select_btn):
            base_style = self._tool_button_base_styles.get(btn, "")
            is_active = btn is active_button
            if is_active:
                extra = f"""
                PushButton {{
                    background: {active_bg};
                    color: {active_fg};
                    border: 1px solid {active_border};
                }}
                PushButton:hover {{
                    background: {active_hover};
                    border: 1px solid {active_border};
                }}
                PushButton:pressed {{
                    background: {active_pressed};
                    border: 1px solid {active_border};
                }}
                """
            else:
                extra = f"""
                PushButton {{
                    background: {inactive_bg};
                    color: {inactive_fg};
                    border: 1px solid {inactive_border};
                }}
                PushButton:hover {{
                    background: {inactive_hover};
                }}
                PushButton:pressed {{
                    background: {inactive_pressed};
                }}
                """
            btn.setStyleSheet(base_style + "\n" + extra)

    def _apply_auto_focus_state(self, enabled: bool) -> None:
        enabled = bool(enabled)
        self.canvas.set_auto_focus_enabled(enabled)
        self.focus_timer.stop()
        if not enabled:
            self._soft_focus_target = None
        if enabled:
            self.canvas_hint.setText("支持鼠标与触控笔。可先右键拖动画布定位，写完后自动回到内容重心。")
        else:
            self.canvas_hint.setText("支持鼠标与触控笔。可按住鼠标右键拖动画布，停笔后保持当前位置。")
        self._set_active_tool(self.canvas.current_tool)

    def _set_active_tool(self, tool: HandwritingTool) -> None:
        self.canvas.set_tool(tool)
        auto_focus = self.auto_focus_checkbox.isChecked() if hasattr(self, "auto_focus_checkbox") else False
        labels = {
            HandwritingTool.WRITE: (
                "书写中",
                "直接书写，停笔后自动识别；可先右键拖动画布"
                + ("，识别后自动回到内容重心" if auto_focus else "，并保持当前位置"),
            ),
            HandwritingTool.ERASE: ("橡皮模式", "像素级局部擦除命中的笔迹片段，保留其余部分"),
            HandwritingTool.SELECT_CORRECT: ("圈选修正", "自由圈选后只擦除圈内笔段，便于局部重写"),
        }
        status, hint = labels.get(tool, ("就绪", ""))
        self.status_label.setText(status)
        self.mode_hint_label.setText(hint)
        active_buttons = {
            HandwritingTool.WRITE: self.write_btn,
            HandwritingTool.ERASE: self.erase_btn,
            HandwritingTool.SELECT_CORRECT: self.select_btn,
        }
        self._active_tool_button = active_buttons.get(tool)
        self._apply_tool_button_styles()

    def _get_active_model_key(self) -> str:
        parent = self.owner or self.parent()
        model_key = ""
        if parent is not None and hasattr(parent, "_get_preferred_model_for_predict"):
            try:
                model_key = str(parent._get_preferred_model_for_predict() or "").strip().lower()
            except Exception:
                model_key = ""
        if parent is not None and hasattr(parent, "current_model"):
            try:
                if not model_key:
                    model_key = str(getattr(parent, "current_model") or "").strip().lower()
            except Exception:
                model_key = ""
        if not model_key and hasattr(self.model, "_default_model"):
            try:
                model_key = str(getattr(self.model, "_default_model") or "").strip().lower()
            except Exception:
                model_key = ""
        valid = {"mathcraft", "mathcraft_text", "mathcraft_mixed", "external_model"}
        return model_key if model_key in valid else "mathcraft"

    def _get_active_model_label(self) -> str:
        labels = {
            "mathcraft": "公式",
            "mathcraft_text": "文字",
            "mathcraft_mixed": "混合",
        }
        model_key = self._get_active_model_key()
        if model_key == "external_model":
            owner = self.owner
            if owner is not None and hasattr(owner, "_get_status_model_display_name"):
                try:
                    display = str(owner._get_status_model_display_name() or "").strip()
                    if display:
                        return display
                except Exception:
                    pass
            cfg = self._get_external_model_config()
            if cfg is not None:
                try:
                    if cfg.normalized_provider() == "mineru":
                        return "MinerU"
                    model_name = cfg.normalized_model_name()
                    if model_name:
                        return model_name
                except Exception:
                    pass
            return "外部模型"
        return labels.get(model_key, "公式")

    def _get_external_model_config(self):
        owner = self.owner
        if owner is None or not hasattr(owner, "_get_external_model_config"):
            return None
        try:
            return owner._get_external_model_config()
        except Exception:
            return None

    def _is_external_model_ready(self) -> bool:
        owner = self.owner
        if owner is None or not hasattr(owner, "_is_external_model_configured"):
            return False
        try:
            return bool(owner._is_external_model_configured())
        except Exception:
            return False

    def _refresh_recognition_context(self) -> None:
        if hasattr(self, "recognition_type_label"):
            self.recognition_type_label.setText(f"当前识别类型：{self._get_active_model_label()}")
        self._update_layout_button_state()

    def _update_layout_button_state(self) -> None:
        if not hasattr(self, "layout_btn"):
            return
        active_model = self._get_active_model_key()
        available = (active_model != "external_model" or self._is_external_model_ready()) and not self._closing
        busy = self._is_layout_busy()
        self.layout_btn.setEnabled(not busy and not self._closing)
        self.layout_btn.setText("排版中..." if self._is_layout_busy() else "自动排版")
        opacity = 1.0 if available or busy else 0.55
        effect = getattr(self, "_layout_btn_opacity", None)
        if effect is not None:
            effect.setOpacity(opacity)

    def _on_canvas_changed(self) -> None:
        if self.canvas.store.is_empty():
            self.status_label.setText("就绪")
            return
        self._schedule_recognition()

    def _schedule_recognition(self) -> None:
        if self._recognizing:
            self._recognize_pending = True
            self.status_label.setText("更新中，等待当前识别完成...")
            return
        self.recognize_timer.start(700)
        self.status_label.setText("书写中")

    def _run_recognition(self) -> None:
        self._refresh_recognition_context()
        if self._recognizing:
            self._recognize_pending = True
            return
        if self._is_owner_recognition_busy():
            self._recognize_pending = True
            self.recognize_timer.start(800)
            self.status_label.setText("主窗口识别中，等待继续...")
            self._show_busy_notice()
            return
        export = self.canvas.export_image()
        if export.is_empty or export.image is None:
            self.status_label.setText("画布为空")
            self._show_warning("没有可识别内容", "先写入笔迹后再尝试识别。")
            return

        active_model = self._get_active_model_key()
        external_config = None
        if active_model == "external_model":
            if not self._is_external_model_ready():
                self.status_label.setText("外部模型未配置")
                owner = self.owner
                hint = "请先在设置中完成外部模型配置并测试连接。"
                if owner is not None and hasattr(owner, "_get_external_model_required_fields_hint"):
                    try:
                        hint = str(owner._get_external_model_required_fields_hint() or hint)
                    except Exception:
                        pass
                self._show_warning("外部模型未配置", hint)
                if owner is not None and hasattr(owner, "open_settings"):
                    try:
                        owner.open_settings()
                    except Exception:
                        pass
                return
            external_config = self._get_external_model_config()

        self._recognizing = True
        self._recognize_pending = False
        self.status_label.setText("识别中")
        self._recognize_thread = QThread()
        self._recognize_worker = HandwritingRecognitionWorker(
            self.model,
            export.image,
            model_name=active_model,
            external_config=external_config,
        )
        thread = self._recognize_thread
        worker = self._recognize_worker
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_recognition_finished)
        worker.failed.connect(self._on_recognition_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._teardown_recognition)
        thread.start()

    def _teardown_recognition(self, *_args) -> None:
        self._recognize_thread = None
        self._recognize_worker = None
        self._recognizing = False
        if self._closing:
            return
        if self._recognize_pending:
            self._recognize_pending = False
            self._schedule_recognition()

    def _on_recognition_finished(self, latex: str) -> None:
        if self._closing:
            return
        text = self._normalize_result_display_text((latex or "").strip())
        self._last_result = text
        self.result_editor.blockSignals(True)
        self.result_editor.setPlainText(text)
        self.result_editor.blockSignals(False)
        self._refresh_preview_from_text(text)
        self.status_label.setText("已更新")
        self._update_layout_button_state()

    def _on_recognition_failed(self, error: str) -> None:
        if self._closing:
            return
        brief = (error or "识别失败").strip()
        self.status_label.setText(f"识别失败: {brief}")
        brief = brief.rstrip("。.!！？? ")
        self._show_error("手写识别失败", f"{brief}。可手动擦除后重写，或直接编辑右侧 LaTeX 结果。")
        self._update_layout_button_state()

    def _on_result_editor_changed(self) -> None:
        self._refresh_preview_from_text(self.result_editor.toPlainText().strip())

    def _reposition_viewport_to_point(self, point, hard: bool) -> None:
        viewport = self.canvas_scroll.viewport()
        hbar = self.canvas_scroll.horizontalScrollBar()
        vbar = self.canvas_scroll.verticalScrollBar()
        left = hbar.value()
        top = vbar.value()
        right = left + viewport.width()
        bottom = top + viewport.height()
        margin_x = max(96, viewport.width() // 7)
        margin_y = max(88, viewport.height() // 7)
        target_x = left
        target_y = top
        px = point.x()
        py = point.y()
        if px > right - margin_x:
            target_x = int(px - viewport.width() * 0.62)
        elif px < left + margin_x:
            target_x = int(px - viewport.width() * 0.38)
        if py > bottom - margin_y:
            target_y = int(py - viewport.height() * 0.62)
        elif py < top + margin_y:
            target_y = int(py - viewport.height() * 0.38)
        if target_x == left and target_y == top and not hard:
            return
        if hard:
            self._h_scroll_anim.stop()
            self._v_scroll_anim.stop()
            hbar.setValue(max(hbar.minimum(), min(target_x, hbar.maximum())))
            vbar.setValue(max(vbar.minimum(), min(target_y, vbar.maximum())))
            return
        self._animate_scroll(target_x, target_y, duration=240)

    def _schedule_soft_focus(self, point) -> None:
        if not self.auto_focus_checkbox.isChecked():
            return
        self._soft_focus_target = point
        delay = self.focus_timer.interval()
        if self.recognize_timer.isActive():
            delay = max(delay, self.recognize_timer.remainingTime() + 320)
        self.focus_timer.start(delay)

    def _apply_soft_focus(self) -> None:
        if not self.auto_focus_checkbox.isChecked() or self._soft_focus_target is None:
            return
        point = self._soft_focus_target
        self._soft_focus_target = None
        viewport = self.canvas_scroll.viewport()
        target_x = int(point.x() - viewport.width() * 0.5)
        target_y = int(point.y() - viewport.height() * 0.46)
        self._animate_scroll(target_x, target_y, duration=280)

    def _pan_canvas_view(self, dx: int, dy: int) -> None:
        self.focus_timer.stop()
        self._soft_focus_target = None
        self._h_scroll_anim.stop()
        self._v_scroll_anim.stop()
        hbar = self.canvas_scroll.horizontalScrollBar()
        vbar = self.canvas_scroll.verticalScrollBar()
        hbar.setValue(max(hbar.minimum(), min(hbar.value() + dx, hbar.maximum())))
        vbar.setValue(max(vbar.minimum(), min(vbar.value() + dy, vbar.maximum())))

    def _animate_scroll(self, target_x: int, target_y: int, duration: int) -> None:
        hbar = self.canvas_scroll.horizontalScrollBar()
        vbar = self.canvas_scroll.verticalScrollBar()
        target_x = max(hbar.minimum(), min(target_x, hbar.maximum()))
        target_y = max(vbar.minimum(), min(target_y, vbar.maximum()))
        if abs(target_x - hbar.value()) > 1:
            self._h_scroll_anim.stop()
            self._h_scroll_anim.setDuration(duration)
            self._h_scroll_anim.setStartValue(hbar.value())
            self._h_scroll_anim.setEndValue(target_x)
            self._h_scroll_anim.start()
        if abs(target_y - vbar.value()) > 1:
            self._v_scroll_anim.stop()
            self._v_scroll_anim.setDuration(duration)
            self._v_scroll_anim.setStartValue(vbar.value())
            self._v_scroll_anim.setEndValue(target_y)
            self._v_scroll_anim.start()

    def _refresh_preview_from_text(self, latex: str) -> None:
        preview_text = self._normalize_preview_source_text(latex)
        if self.preview_view is None:
            if self.preview_fallback is not None:
                self.preview_fallback.setText("WebEngine 不可用。\n\n当前内容:\n" + (preview_text or "<empty>"))
            return
        html_text = self._build_math_html(preview_text, dark=bool(isDarkTheme()))
        base_url = self._mathjax_base_url()
        try:
            self.preview_view.setHtml(html_text, base_url)
        except Exception:
            pass

    def _build_math_html(self, latex: str, dark: bool) -> str:
        content = latex.strip()
        if dark:
            body_bg = "#11161d"
            body_text = "#edf2f7"
            empty_border = "#3c4757"
            empty_text = "#9ca7b7"
            text_bg = "rgba(255,255,255,0.03)"
            math_bg = "rgba(255,255,255,0.02)"
        else:
            body_bg = "#ffffff"
            body_text = "#111827"
            empty_border = "#d1d5db"
            empty_text = "#6b7280"
            text_bg = "#f8fafc"
            math_bg = "#ffffff"
        if content:
            body = self._build_preview_body(content)
        else:
            body = '<div class="empty">写完后会在这里看到预览</div>'
        return f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <style>
    html, body {{ margin: 0; padding: 0; min-height: 100%; background: {body_bg}; color: {body_text}; overflow: auto; }}
    body {{ box-sizing: border-box; padding: 16px; font-family: 'Segoe UI', sans-serif; }}
    .content {{ display: flex; flex-direction: column; gap: 12px; align-items: stretch; min-height: 100%; }}
    .text-block {{
      white-space: pre-wrap;
      word-break: break-word;
      overflow-wrap: anywhere;
      line-height: 1.55;
      font-size: 18px;
      padding: 4px 6px;
      border-radius: 10px;
      background: {text_bg};
    }}
    .math-block {{
      padding: 8px 4px;
      border-radius: 10px;
      background: {math_bg};
      overflow-x: auto;
      overflow-y: hidden;
    }}
    .spacer {{ height: 4px; flex: 0 0 auto; }}
    .empty {{ color: {empty_text}; min-height: 220px; display: flex; align-items: center; justify-content: center; border: 1px dashed {empty_border}; border-radius: 12px; }}
  </style>
  <script>
    window.MathJax = {{ tex: {{ inlineMath: [['$', '$'], ['\\(', '\\)']] }}, svg: {{ fontCache: 'global' }} }};
  </script>
  <script src=\"MathJax-3.2.2/es5/tex-svg.js\"></script>
</head>
<body>
{body}
</body>
</html>
"""

    def _normalize_preview_source_text(self, text: str) -> str:
        content = str(text or "").replace("\r\n", "\n").strip()
        if not content:
            return ""
        if self._preview_output_mode() != "latex":
            return content
        lines: list[str] = []
        for raw_line in content.split("\n"):
            stripped = raw_line.strip()
            if not stripped:
                if lines and lines[-1] != "":
                    lines.append("")
                continue
            lines.append(self._unwrap_math_delimiters(stripped))
        return "\n".join(lines).strip()

    def _normalize_result_display_text(self, text: str) -> str:
        content = str(text or "").replace("\r\n", "\n").strip()
        if not content:
            return ""
        if self._preview_output_mode() != "latex":
            return content
        return self._normalize_preview_source_text(content)

    def _preview_output_mode(self) -> str:
        if self._get_active_model_key() != "external_model":
            return "latex"
        cfg = self._get_external_model_config()
        if cfg is None:
            return "latex"
        try:
            return cfg.normalized_output_mode()
        except Exception:
            return "latex"

    def _build_preview_body(self, content: str) -> str:
        mode = self._preview_output_mode()
        if mode != "latex":
            return f'<div class="content"><div class="text-block">{html.escape(content)}</div></div>'
        parts: list[str] = ['<div class="content">']
        for raw_line in content.split("\n"):
            line = raw_line.strip()
            if not line:
                parts.append('<div class="spacer"></div>')
                continue
            normalized = self._unwrap_math_delimiters(line)
            if self._looks_like_math_line(line, normalized):
                parts.append(f'<div class="math-block">\\[{html.escape(normalized)}\\]</div>')
            else:
                parts.append(f'<div class="text-block">{html.escape(line)}</div>')
        parts.append("</div>")
        return "".join(parts)

    def _unwrap_math_delimiters(self, text: str) -> str:
        value = str(text or "").strip()
        if not value:
            return ""
        fence_match = re.fullmatch(r"```(?:latex|tex|math)?\s*(.*?)\s*```", value, flags=re.IGNORECASE | re.DOTALL)
        if fence_match:
            value = fence_match.group(1).strip()
        pairs = (("$$", "$$"), (r"\[", r"\]"), (r"\(", r"\)"), ("$", "$"))
        for left, right in pairs:
            if value.startswith(left) and value.endswith(right):
                inner = value[len(left): len(value) - len(right)].strip()
                if inner:
                    return inner
        return value

    def _looks_like_math_line(self, raw_line: str, normalized_line: str) -> bool:
        raw = str(raw_line or "").strip()
        line = str(normalized_line or "").strip()
        if not line:
            return False
        if raw != line:
            return True
        math_tokens = (
            "\\", "^", "_", "=",
            "<", ">", "≤", "≥", "≈", "≠", "∈", "∑", "∫", "∞",
        )
        if any(token in line for token in math_tokens):
            return True
        compact = line.replace(" ", "")
        if re.search(r"[A-Za-z]\([A-Za-z]", compact):
            return True
        if re.search(r"\b(?:dim|deg|lim|ker|coker|Hom|Ext|Tor)\b", line):
            return True
        return False

    def _mathjax_base_url(self) -> QUrl:
        assets_dir = Path(resource_path("assets")).resolve()
        return QUrl.fromLocalFile(str(assets_dir) + "/")

    def _clear_all(self) -> None:
        self.canvas.clear_canvas()
        self.result_editor.blockSignals(True)
        self.result_editor.clear()
        self.result_editor.blockSignals(False)
        self._refresh_preview_from_text("")
        self.status_label.setText("已清空")

    def _undo(self) -> None:
        if self.canvas.undo():
            self.status_label.setText("已撤销")

    def _redo(self) -> None:
        if self.canvas.redo():
            self.status_label.setText("已重做")

    def _insert_result(self) -> None:
        text = self.result_editor.toPlainText().strip()
        if not text:
            self.status_label.setText("没有可插入的内容")
            self._show_warning("当前无内容", "请先识别或手动编辑 LaTeX 后再插入。")
            return
        self.latexInserted.emit(text)
        self.status_label.setText("已插入主窗口，当前内容已保留")
        self._show_info("已插入", "结果已写入主窗口，当前手写窗口内容已保留。")

    def _copy_result(self) -> None:
        text = self.result_editor.toPlainText().strip()
        if not text:
            self.status_label.setText("没有可复制的内容")
            self._show_warning("当前无内容", "请先识别或手动编辑 LaTeX 后再复制。")
            return
        QApplication.clipboard().setText(text)
        self.status_label.setText("已复制 LaTeX")
        self._show_info("已复制", "LaTeX 已复制到剪贴板。")

    def _build_math_document_prompt(self, recognized_text: str) -> str:
        base = (
            "你是一个数学文档排版助手。"
            "请根据图片中的手写数学内容，整理为一份完整、可编译、结构清晰的 XeLaTeX 文档源码。"
            "输出必须是完整的 .tex 文档，不要解释，不要添加说明，不要输出 markdown 代码块。"
            "文档类固定使用 \\documentclass[UTF8]{ctexart}。"
            "默认只使用 amsmath, amssymb, amsthm, mathtools, bm, geometry, graphicx, booktabs, array, multirow。"
            "只有在图片中明确存在示意图且无法用普通公式表达时，才允许额外使用 tikz。"
            "必须包含导言区与 \\begin{document}...\\end{document}。"
            "严格保持原始数学含义，不要擅自补充证明、解释、例子。"
            "不确定内容可用 TeX 注释 % TODO: ... 标记。"
        )
        draft = str(recognized_text or "").strip()
        if not draft:
            return base
        return base + "\n\n以下是当前识别草稿文本，请优先参考它修正文档结构，但图片仍是最终依据：\n" + draft

    def _auto_layout_document(self) -> None:
        if self._closing:
            return
        active_model = self._get_active_model_key()
        if active_model == "external_model" and not self._is_external_model_ready():
            self.status_label.setText("外部模型未配置")
            self._show_warning("外部模型未配置", "请先完成外部模型配置并测试连接。")
            return
        if self._recognizing:
            self.status_label.setText("等待识别完成后排版")
            self._show_info("正在识别", "请等待当前手写识别完成后再自动排版。")
            return
        if self._is_layout_busy():
            self.status_label.setText("自动排版中")
            self._show_info("排版中", "自动排版任务正在进行，请稍候。")
            return
        if active_model != "external_model":
            draft = self.result_editor.toPlainText().strip()
            if not draft:
                self.status_label.setText("没有可排版内容")
                self._show_warning("没有可排版内容", "请先写入笔迹并完成识别，或补充可编辑的 TeX 草稿。")
                return
            self._open_document_preview(draft)
            self.status_label.setText("已打开文档编辑")
            self._show_info("已打开文档编辑", "当前为本地模型模式，可继续编辑源码并编译 PDF。")
            return
        export = self.canvas.export_image()
        if export.is_empty or export.image is None:
            self.status_label.setText("没有可排版内容")
            self._show_warning("没有可排版内容", "请先写入笔迹并完成识别。")
            return
        cfg = self._get_external_model_config()
        if cfg is None:
            self.status_label.setText("外部模型未配置")
            self._show_warning("外部模型未配置", "请先完成外部模型配置并测试连接。")
            return
        runtime_cfg = replace(
            cfg,
            output_mode="text",
            prompt_template="math_document_layout_v1",
            custom_prompt=self._build_math_document_prompt(self.result_editor.toPlainText().strip()),
        )
        self.status_label.setText("自动排版中")
        self._layout_thread = QThread()
        self._layout_worker = _HandwritingDocumentLayoutWorker(runtime_cfg, export.image)
        worker = self._layout_worker
        thread = self._layout_thread
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_document_layout_finished)
        worker.failed.connect(self._on_document_layout_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._teardown_layout)
        thread.start()
        self._update_layout_button_state()

    def _open_document_preview(self, doc_text: str) -> None:
        if self._document_preview_window is None:
            self._document_preview_window = DocumentPreviewWindow()
        self._document_preview_window.set_document(doc_text)
        self._document_preview_window.show()
        self._document_preview_window.raise_()
        self._document_preview_window.activateWindow()

    def _teardown_layout(self, *_args) -> None:
        self._layout_thread = None
        self._layout_worker = None
        if not self._closing and self.status_label.text() == "自动排版中":
            self.status_label.setText("已更新")
        self._update_layout_button_state()

    def _on_document_layout_finished(self, text: str) -> None:
        if self._closing:
            return
        doc_text = str(text or "").strip()
        if not doc_text:
            self.status_label.setText("排版结果为空")
            self._show_warning("排版结果为空", "外部模型未返回可用的 TeX 文档。")
            return
        self._open_document_preview(doc_text)
        self.status_label.setText("自动排版完成")
        self._show_info("自动排版完成", "外部模型已生成可编辑的 TeX 文档窗口。")

    def _on_document_layout_failed(self, error: str) -> None:
        if self._closing:
            return
        brief = (error or "自动排版失败").strip()
        self.status_label.setText(f"排版失败: {brief}")
        self._show_error("自动排版失败", brief)

    def _is_layout_busy(self) -> bool:
        return bool(self._layout_thread is not None and self._layout_thread.isRunning())

    def is_recognizing_busy(self) -> bool:
        return bool(
            self._recognizing
            or (self._recognize_thread is not None and self._recognize_thread.isRunning())
        )

    def _is_owner_recognition_busy(self) -> bool:
        owner = self.owner
        if owner is None or not hasattr(owner, "is_recognition_busy"):
            return False
        try:
            return bool(owner.is_recognition_busy(source="handwriting"))
        except Exception:
            return False

    def _show_busy_notice(self) -> None:
        now = time.monotonic()
        if now - self._last_busy_notice_ts < 1.5:
            return
        self._last_busy_notice_ts = now
        self._show_info("正在识别", "主窗口正在识别，请稍候。")

    def _show_info(self, title: str, content: str) -> None:
        InfoBar.info(title=title, content=content, orient=Qt.Orientation.Vertical, isClosable=True, position=InfoBarPosition.TOP, duration=2800, parent=self)

    def _show_warning(self, title: str, content: str) -> None:
        InfoBar.warning(title=title, content=content, orient=Qt.Orientation.Vertical, isClosable=True, position=InfoBarPosition.TOP, duration=3200, parent=self)

    def _show_error(self, title: str, content: str) -> None:
        InfoBar.error(title=title, content=content, orient=Qt.Orientation.Vertical, isClosable=True, position=InfoBarPosition.TOP, duration=4200, parent=self)

    def closeEvent(self, event) -> None:
        self._closing = True
        self.recognize_timer.stop()
        self.focus_timer.stop()
        self._h_scroll_anim.stop()
        self._v_scroll_anim.stop()
        layout_thread = self._layout_thread
        if layout_thread is not None:
            try:
                layout_thread.requestInterruption()
            except Exception:
                pass
            try:
                layout_thread.quit()
            except Exception:
                pass
            try:
                layout_thread.wait(150)
            except Exception:
                pass
        thread = self._recognize_thread
        if thread is not None:
            try:
                thread.requestInterruption()
            except Exception:
                pass
            try:
                thread.quit()
            except Exception:
                pass
            try:
                thread.wait(150)
            except Exception:
                pass
        super().closeEvent(event)
