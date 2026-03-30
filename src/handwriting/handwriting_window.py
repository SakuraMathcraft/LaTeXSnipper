from __future__ import annotations

import math
import time
from pathlib import Path

from PyQt6.QtCore import QEasingCurve, QEvent, QPropertyAnimation, QThread, QTimer, QUrl, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QWheelEvent
from PyQt6.QtWidgets import QApplication, QCheckBox, QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QScrollArea, QSplitter, QVBoxLayout, QWidget
from qfluentwidgets import FluentIcon, InfoBar, InfoBarPosition, PrimaryPushButton, PushButton, isDarkTheme

from .ink_canvas import InkCanvas
from .recognizer import HandwritingRecognitionWorker
from .tools import HandwritingTool
from utils import resource_path

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
except Exception:  # pragma: no cover
    QWebEngineView = None

try:
    from PyQt6.QtWebEngineCore import QWebEngineSettings
except Exception:  # pragma: no cover
    QWebEngineSettings = None


class SlowZoomPlainTextEdit(QPlainTextEdit):
    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta:
                self.zoomIn(1 if delta > 0 else -1)
                event.accept()
                return
        super().wheelEvent(event)


if QWebEngineView is not None:
    class SlowZoomWebView(QWebEngineView):
        def wheelEvent(self, event: QWheelEvent) -> None:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                delta = event.angleDelta().y()
                if delta:
                    step = 0.08 if delta > 0 else -0.08
                    self.setZoomFactor(max(0.5, min(3.0, self.zoomFactor() + step)))
                    event.accept()
                    return
            super().wheelEvent(event)
else:
    SlowZoomWebView = None


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
        self._last_result = ""
        self._theme_is_dark_cached = None
        self._ui_ready = False
        self._soft_focus_target = None
        self._last_busy_notice_ts = 0.0
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

        splitter = QSplitter()
        splitter.setObjectName("handwritingSplitter")
        splitter.setHandleWidth(14)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 10, 0)
        left_layout.setSpacing(6)
        self.canvas_title = QLabel("手写画布")
        self.canvas_title.setObjectName("handwritingSectionTitle")
        self.canvas_hint = QLabel("支持鼠标与触控笔。关闭自动聚焦后，可按住鼠标右键拖动画布。")
        self.canvas_hint.setObjectName("handwritingHint")
        left_layout.addWidget(self.canvas_title)
        left_layout.addWidget(self.canvas_hint)
        self.canvas = InkCanvas(self)
        self.canvas.set_auto_focus_enabled(False)
        self.canvas_scroll = QScrollArea(self)
        self.canvas_scroll.setObjectName("handwritingCanvasScroll")
        self.canvas_scroll.setWidgetResizable(False)
        self.canvas_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.canvas_scroll.setWidget(self.canvas)
        left_layout.addWidget(self.canvas_scroll, 1)
        splitter.addWidget(left)

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
        self.result_editor = SlowZoomPlainTextEdit(self)
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
        if SlowZoomWebView is not None:
            self.preview_view = SlowZoomWebView(self)
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
        splitter.addWidget(right)
        splitter.setSizes([610, 470])
        root.addWidget(splitter, 1)

        bottom = QHBoxLayout()
        self.status_label = QLabel("就绪")
        self.status_label.setObjectName("handwritingStatus")
        bottom.addWidget(self.status_label)
        bottom.addStretch(1)
        self.copy_btn = PushButton(FluentIcon.COPY, "复制 LaTeX")
        self.cancel_btn = PushButton(FluentIcon.CLOSE, "取消")
        self.insert_btn = PrimaryPushButton(FluentIcon.ACCEPT, "插入")
        self.copy_btn.setFixedHeight(34)
        self.cancel_btn.setFixedHeight(34)
        self.insert_btn.setFixedHeight(34)
        bottom.addWidget(self.copy_btn)
        bottom.addWidget(self.cancel_btn)
        bottom.addWidget(self.insert_btn)
        root.addLayout(bottom)

        self.recognize_timer = QTimer(self)
        self.recognize_timer.setSingleShot(True)
        self.focus_timer = QTimer(self)
        self.focus_timer.setSingleShot(True)
        self.focus_timer.setInterval(220)
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

    def _wire_events(self) -> None:
        self.write_btn.clicked.connect(lambda: self._set_active_tool(HandwritingTool.WRITE))
        self.erase_btn.clicked.connect(lambda: self._set_active_tool(HandwritingTool.ERASE))
        self.select_btn.clicked.connect(lambda: self._set_active_tool(HandwritingTool.SELECT_CORRECT))
        self.clear_btn.clicked.connect(self._clear_all)
        self.undo_btn.clicked.connect(self._undo)
        self.redo_btn.clicked.connect(self._redo)
        self.copy_btn.clicked.connect(self._copy_result)
        self.cancel_btn.clicked.connect(self.reject)
        self.insert_btn.clicked.connect(self._insert_result)
        self.auto_focus_checkbox.toggled.connect(self._apply_auto_focus_state)
        self.canvas.contentChanged.connect(self._on_canvas_changed)
        self.canvas.viewportFollowRequested.connect(self._follow_canvas_point)
        self.canvas.contentFocusRequested.connect(self._schedule_soft_focus)
        self.canvas.panRequested.connect(self._pan_canvas_view)
        self.canvas.canvasShifted.connect(self._on_canvas_shifted)
        self.canvas.zoomChanged.connect(lambda _z: QTimer.singleShot(0, self._sync_canvas_extent_to_viewport))
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
            border = "#344151"
            text = "#eef2f7"
            subtext = "#a9b4c3"
            editor_bg = "#151a22"
            editor_border = "rgba(110, 130, 156, 0.45)"
            cb_text = "#c8d1dc"
            card_bg = "#151b23"
            panel_bg = "#121821"
            subpanel_bg = "#121821"
            divider = "rgba(91, 111, 138, 0.24)"
        else:
            bg = "#f5f7fb"
            border = "#d9e0e8"
            text = "#16202a"
            subtext = "#6b7787"
            editor_bg = "#ffffff"
            editor_border = "rgba(148, 163, 184, 0.55)"
            cb_text = "#334155"
            card_bg = "#ffffff"
            panel_bg = "#f8fafc"
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
            self.canvas_hint.setText("支持鼠标与触控笔。已开启自动聚焦，右键拖动画布暂不可用。")
        else:
            self.canvas_hint.setText("支持鼠标与触控笔。关闭自动聚焦后，可按住鼠标右键拖动画布。")
        self._set_active_tool(self.canvas.current_tool)

    def _set_active_tool(self, tool: HandwritingTool) -> None:
        self.canvas.set_tool(tool)
        auto_focus = self.auto_focus_checkbox.isChecked() if hasattr(self, "auto_focus_checkbox") else False
        labels = {
            HandwritingTool.WRITE: (
                "书写中",
                "直接书写，停笔后自动识别" + ("，并温和聚焦到公式中心" if auto_focus else "；右键可拖动画布"),
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
        if parent is not None and hasattr(parent, "current_model"):
            try:
                model_key = str(getattr(parent, "current_model") or "").strip().lower()
            except Exception:
                model_key = ""
        if not model_key and hasattr(self.model, "_default_model"):
            try:
                model_key = str(getattr(self.model, "_default_model") or "").strip().lower()
            except Exception:
                model_key = ""
        valid = {"pix2text", "pix2text_text", "pix2text_mixed", "pix2text_page", "pix2text_table"}
        return model_key if model_key in valid else "pix2text"

    def _get_active_model_label(self) -> str:
        labels = {
            "pix2text": "公式",
            "pix2text_text": "文字",
            "pix2text_mixed": "混合",
            "pix2text_page": "整页",
            "pix2text_table": "表格",
        }
        return labels.get(self._get_active_model_key(), "公式")

    def _refresh_recognition_context(self) -> None:
        if hasattr(self, "recognition_type_label"):
            self.recognition_type_label.setText(f"当前识别类型：{self._get_active_model_label()}")

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
        self._recognizing = True
        self._recognize_pending = False
        self.status_label.setText("识别中")
        self._recognize_thread = QThread(self)
        self._recognize_worker = HandwritingRecognitionWorker(
            self.model,
            export.image,
            model_name=self._get_active_model_key(),
        )
        self._recognize_worker.moveToThread(self._recognize_thread)
        self._recognize_thread.started.connect(self._recognize_worker.run)
        self._recognize_worker.finished.connect(self._on_recognition_finished)
        self._recognize_worker.failed.connect(self._on_recognition_failed)
        self._recognize_worker.finished.connect(self._teardown_recognition)
        self._recognize_worker.failed.connect(self._teardown_recognition)
        self._recognize_thread.start()

    def _teardown_recognition(self, *_args) -> None:
        thread = self._recognize_thread
        worker = self._recognize_worker
        self._recognize_thread = None
        self._recognize_worker = None
        self._recognizing = False
        if worker is not None:
            try:
                worker.deleteLater()
            except Exception:
                pass
        if thread is not None:
            try:
                thread.quit()
                thread.wait(2000)
                thread.deleteLater()
            except Exception:
                pass
        if self._recognize_pending:
            self._recognize_pending = False
            self._schedule_recognition()

    def _on_recognition_finished(self, latex: str) -> None:
        text = (latex or "").strip()
        self._last_result = text
        self.result_editor.blockSignals(True)
        self.result_editor.setPlainText(text)
        self.result_editor.blockSignals(False)
        self._refresh_preview_from_text(text)
        self.status_label.setText("已更新")

    def _on_recognition_failed(self, error: str) -> None:
        brief = (error or "识别失败").strip()
        self.status_label.setText(f"识别失败: {brief}")
        self._show_error("手写识别失败", f"{brief}。可手动擦除后重写，或直接编辑右侧 LaTeX 结果。")

    def _on_result_editor_changed(self) -> None:
        self._refresh_preview_from_text(self.result_editor.toPlainText().strip())

    def _follow_canvas_point(self, point, hard: bool) -> None:
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
            target_x = int(px - viewport.width() * 0.72)
        elif px < left + margin_x:
            target_x = int(px - viewport.width() * 0.28)
        if py > bottom - margin_y:
            target_y = int(py - viewport.height() * 0.72)
        elif py < top + margin_y:
            target_y = int(py - viewport.height() * 0.28)
        if target_x == left and target_y == top and not hard:
            return
        self._animate_scroll(target_x, target_y, duration=180 if hard else 240)

    def _schedule_soft_focus(self, point) -> None:
        if not self.auto_focus_checkbox.isChecked():
            return
        self._soft_focus_target = point
        self.focus_timer.start()

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
        if self.auto_focus_checkbox.isChecked():
            return
        self.focus_timer.stop()
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
        if self.preview_view is None:
            if self.preview_fallback is not None:
                self.preview_fallback.setText("WebEngine 不可用。\n\n当前内容:\n" + (latex or "<empty>"))
            return
        html_text = self._build_math_html(latex, dark=bool(isDarkTheme()))
        base_url = self._mathjax_base_url()
        try:
            self.preview_view.setHtml(html_text, base_url)
        except Exception:
            pass

    def _build_math_html(self, latex: str, dark: bool) -> str:
        formula = latex.strip()
        if dark:
            body_bg = "#11161d"
            body_text = "#edf2f7"
            empty_border = "#3c4757"
            empty_text = "#9ca7b7"
        else:
            body_bg = "#ffffff"
            body_text = "#111827"
            empty_border = "#d1d5db"
            empty_text = "#6b7280"
        if formula:
            body = f'<div class="formula">$${formula}$$</div>'
        else:
            body = '<div class="empty">写完后会在这里看到预览</div>'
        return f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <style>
    body {{ margin: 0; padding: 16px; background: {body_bg}; color: {body_text}; font-family: 'Segoe UI', sans-serif; }}
    .formula {{ font-size: 28px; min-height: 220px; display: flex; align-items: center; justify-content: center; }}
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
        self.accept()

    def _copy_result(self) -> None:
        text = self.result_editor.toPlainText().strip()
        if not text:
            self.status_label.setText("没有可复制的内容")
            self._show_warning("当前无内容", "请先识别或手动编辑 LaTeX 后再复制。")
            return
        QApplication.clipboard().setText(text)
        self.status_label.setText("已复制 LaTeX")
        self._show_info("已复制", "LaTeX 已复制到剪贴板。")

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
        self.recognize_timer.stop()
        self.focus_timer.stop()
        self._h_scroll_anim.stop()
        self._v_scroll_anim.stop()
        thread = self._recognize_thread
        if thread is not None:
            try:
                thread.requestInterruption()
            except Exception:
                pass
        super().closeEvent(event)
