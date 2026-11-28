from __future__ import annotations

import time
from dataclasses import replace
from typing import TYPE_CHECKING

from PyQt6.QtCore import QEvent, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QCloseEvent, QGuiApplication, QIcon, QShowEvent
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    PrimaryPushButton,
    PushButton,
    isDarkTheme,
)

from localization.manager import translate as tr
from recognition.model_policy import resolve_document_recognition_model
from runtime.app_paths import resource_path
from runtime.background_task import BackgroundTask

from .canvas_panel import HandwritingCanvasPanel
from .recognizer import HandwritingRecognitionWorker
from .result_panel import HandwritingResultPanel
from .tools import HandwritingTool

if TYPE_CHECKING:
    from backend.external_model.schemas import ExternalModelConfig
    from recognition.jobs import RecognitionJobCoordinator
    from ui.controllers.model_runtime import ModelRuntimeController
    from ui.controllers.tasks import RecognitionTaskController


class HandwritingWindow(QWidget):
    latexInserted = pyqtSignal(str, str)
    DEFAULT_SIZE = (1160, 700)
    MINIMUM_SIZE = (1160, 700)

    def __init__(
        self,
        *,
        models: ModelRuntimeController,
        coordinator: RecognitionJobCoordinator,
        tasks: RecognitionTaskController,
        owner: QWidget | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.models = models
        self.coordinator = coordinator
        self.tasks = tasks
        self.owner = owner
        self._recognize_pending = False
        self._recognition_task = BackgroundTask(self)
        self._recognition_task.succeeded.connect(self._on_recognition_finished)
        self._recognition_task.failed.connect(self._on_recognition_failed)
        self._recognition_task.finished.connect(self._teardown_recognition)
        self._closing = False
        self._last_external_output_mode = ""
        self._theme_is_dark_cached: bool | None = None
        self._ui_ready = False
        self._last_busy_notice_ts = 0.0
        self._last_stroke_ts = 0.0
        self._centered_once = False
        self._build_ui()
        self._wire_events()
        self._canvas_panel.set_tool(HandwritingTool.WRITE)
        self.apply_theme_styles(force=True)

    def _build_ui(self) -> None:
        self.setWindowTitle(tr("手写识别"))
        self.setObjectName("handwritingWindow")
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
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        try:
            self.setWindowIcon(QIcon(resource_path("assets/icon.ico")))
        except Exception:
            pass
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)
        title_bar = QHBoxLayout()
        title = QLabel(tr("手写识别"))
        title.setObjectName("handwritingTitle")
        self.mode_hint_label = QLabel(
            tr("当前圈选修正为自由圈选矢量裁剪并保留剩余笔段")
        )
        self.mode_hint_label.setObjectName("handwritingModeHint")
        title_bar.addWidget(title)
        title_bar.addWidget(self.mode_hint_label)
        title_bar.addStretch(1)
        root.addLayout(title_bar)
        splitter = QSplitter()
        splitter.setObjectName("handwritingSplitter")
        splitter.setHandleWidth(14)
        self._canvas_panel = HandwritingCanvasPanel(self)
        splitter.addWidget(self._canvas_panel)
        self._results = HandwritingResultPanel(self)
        splitter.addWidget(self._results)
        splitter.setSizes([610, 470])
        root.addWidget(splitter, 1)
        bottom = QHBoxLayout()
        self.status_label = QLabel(tr("就绪"))
        self.status_label.setObjectName("handwritingStatus")
        bottom.addWidget(self.status_label)
        bottom.addStretch(1)
        self.copy_btn = PushButton(FluentIcon.COPY, tr("复制 LaTeX"))
        self.insert_btn = PrimaryPushButton(FluentIcon.ACCEPT, tr("插入"))
        self.copy_btn.setFixedHeight(34)
        self.insert_btn.setFixedHeight(34)
        bottom.addWidget(self.copy_btn)
        bottom.addWidget(self.insert_btn)
        root.addLayout(bottom)
        self.recognize_timer = QTimer(self)
        self.recognize_timer.setSingleShot(True)
        self.setMinimumSize(*self.MINIMUM_SIZE)
        self.resize(*self.DEFAULT_SIZE)
        self._ui_ready = True

    def _wire_events(self) -> None:
        self._canvas_panel.clear_requested.connect(self._clear_all)
        self._canvas_panel.status_changed.connect(self.status_label.setText)
        self._canvas_panel.mode_hint_changed.connect(self.mode_hint_label.setText)
        self.copy_btn.clicked.connect(self._copy_result)
        self.insert_btn.clicked.connect(self._insert_result)
        self._canvas_panel.canvas.contentChanged.connect(self._on_canvas_changed)
        self._canvas_panel.canvas.strokeFinished.connect(self._on_stroke_finished)
        self._results.text_changed.connect(self._refresh_preview)
        self.recognize_timer.timeout.connect(self._run_recognition)

    def showEvent(self, event: QShowEvent) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        super().showEvent(event)
        self._center_on_owner_screen_once()
        if self._ui_ready:
            self.apply_theme_styles(force=True)

    def _center_on_owner_screen_once(self) -> None:
        if self._centered_once:
            return
        self._centered_once = True
        try:
            screen = None
            handle = self.owner.windowHandle() if self.owner is not None else None
            if handle is not None:
                screen = handle.screen()
            if screen is None:
                screen = QGuiApplication.primaryScreen()
            if screen is None:
                return
            frame = self.frameGeometry()
            frame.moveCenter(screen.availableGeometry().center())
            self.move(frame.topLeft())
        except Exception:
            pass

    def changeEvent(self, event: QEvent) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
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
        if dark:
            bg = "#171c24"
            text = "#eef2f7"
            subtext = "#a9b4c3"
            editor_bg = "#151a22"
            editor_border = "rgba(110, 130, 156, 0.45)"
            card_bg = "#151b23"
            subpanel_bg = "#121821"
            divider = "rgba(91, 111, 138, 0.24)"
        else:
            bg = "#f5f7fb"
            text = "#16202a"
            subtext = "#6b7787"
            editor_bg = "#ffffff"
            editor_border = "rgba(148, 163, 184, 0.55)"
            card_bg = "#ffffff"
            subpanel_bg = "#ffffff"
            divider = "rgba(148, 163, 184, 0.22)"
        self.setStyleSheet(
            f"""
            QWidget#handwritingWindow {{ background: {bg}; }}
            QLabel#handwritingTitle {{ color: {text}; font-size: 24px; font-weight: 600; padding-right: 10px; }}
            QLabel#handwritingModeHint {{ color: {subtext}; font-size: 12px; }}
            QLabel#handwritingSectionTitle {{ color: {text}; font-size: 14px; font-weight: 600; }}
            QLabel#handwritingHint {{ color: {subtext}; font-size: 12px; }}
            QLabel#handwritingStatus {{ color: {subtext}; font-size: 12px; padding-top: 4px; }}
            QPlainTextEdit {{
                background: {editor_bg};
                color: {text};
                border: 1px solid {editor_border};
                border-radius: 10px;
                padding: 8px;
                selection-background-color: {("#2f6fb3" if dark else "#0a84ff")};
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
        self._canvas_panel.apply_theme(dark)
        self._refresh_preview()

    def _get_active_model_key(self) -> str:
        return resolve_document_recognition_model(self.models.current_model)

    def _get_handwriting_external_model_config(self) -> ExternalModelConfig | None:
        cfg = self.models.external_config()
        if cfg is None:
            return None
        try:
            if str(getattr(cfg, "custom_prompt", "") or "").strip():
                return cfg
            return replace(cfg, prompt_template="ocr_handwriting_mixed_v1")
        except Exception:
            return cfg

    def _is_external_model_ready(self) -> bool:
        return self.models.external_configured()

    def _on_canvas_changed(self) -> None:
        if self._canvas_panel.canvas.store.is_empty():
            self.status_label.setText(tr("就绪"))
            return
        self._schedule_recognition()

    def _on_stroke_finished(self) -> None:
        self._last_stroke_ts = time.monotonic()

    def _ms_since_last_stroke(self) -> float:
        return (time.monotonic() - self._last_stroke_ts) * 1000.0

    def _schedule_recognition(self) -> None:
        if self._closing:
            return
        if self._recognition_task.busy:
            self._recognize_pending = True
            self.status_label.setText(tr("更新中，等待当前识别完成..."))
            return
        stroke_count = len(self._canvas_panel.canvas.store.strokes)
        since_last = self._ms_since_last_stroke()
        if since_last < 300 and stroke_count > 3:
            delay = 700
        elif stroke_count <= 2:
            delay = 250
        else:
            delay = 350
        self.recognize_timer.start(delay)
        self.status_label.setText(tr("书写中"))

    def _run_recognition(self) -> None:
        if self._closing:
            return
        if self._recognition_task.busy:
            self._recognize_pending = True
            return
        if self._is_owner_recognition_busy():
            self._recognize_pending = True
            self.recognize_timer.start(800)
            self.status_label.setText(tr("主窗口识别中，等待继续..."))
            self._show_busy_notice()
            return
        export = self._canvas_panel.canvas.export_image()
        if export.is_empty or export.image is None:
            self.status_label.setText(tr("画布为空"))
            self._show_warning(tr("没有可识别内容"), tr("先写入笔迹后再尝试识别。"))
            return
        active_model = self._get_active_model_key()
        external_config = None
        if active_model == "external_model":
            if not self._is_external_model_ready():
                self.status_label.setText(tr("外部模型未配置"))
                owner = self.owner
                if owner is not None:
                    try:
                        self.models.show_external_configuration()
                        return
                    except Exception:
                        pass
                self._show_warning(
                    tr("外部模型未配置"), tr("请先在设置中完成外部模型配置。")
                )
                return
            external_config = self._get_handwriting_external_model_config()
            if external_config is None:
                self.status_label.setText(tr("外部模型未配置"))
                self._show_warning(tr("外部模型未配置"), tr("请先完成必要配置。"))
                return
            self._last_external_output_mode = external_config.resolved_output_mode()
        self._recognize_pending = False
        self.status_label.setText(tr("识别中"))
        worker = HandwritingRecognitionWorker(
            self.coordinator,
            export.image,
            model_name=active_model,
            external_config=external_config,
        )
        self._recognition_task.start(worker)

    def _teardown_recognition(self) -> None:
        if self._closing:
            return
        if self._recognize_pending:
            self._recognize_pending = False
            self._schedule_recognition()

    def _on_recognition_finished(self, latex: str) -> None:
        if self._closing:
            return
        self._results.set_result(latex, self._preview_output_mode())
        self.status_label.setText(tr("已更新"))

    def _on_recognition_failed(self, error: str) -> None:
        if self._closing:
            return
        brief = (error or tr("识别失败")).strip()
        self.status_label.setText(tr("识别失败: {error}").format(error=brief))
        brief = brief.rstrip("。.!！？? ")
        self._show_error(
            tr("手写识别失败"),
            tr("{error}。可手动擦除后重写，或直接编辑右侧 LaTeX 结果。").format(
                error=brief
            ),
        )

    def _refresh_preview(self) -> None:
        self._results.refresh_preview(self._preview_output_mode())

    def _preview_output_mode(self) -> str:
        if self._get_active_model_key() != "external_model":
            return "markdown"
        if self._last_external_output_mode:
            return self._last_external_output_mode
        cfg = self._get_handwriting_external_model_config()
        if cfg is None:
            return "latex"
        return cfg.resolved_output_mode()

    def _clear_all(self) -> None:
        self._canvas_panel.canvas.clear_canvas()
        self._results.set_result("", self._preview_output_mode())
        self.status_label.setText(tr("已清空"))

    def _insert_result(self) -> None:
        text = self._results.text()
        if not text:
            self.status_label.setText(tr("没有可插入的内容"))
            self._show_warning(
                tr("当前无内容"), tr("请先识别或手动编辑 LaTeX 后再插入。")
            )
            return
        self.latexInserted.emit(text, self._preview_output_mode())
        self.status_label.setText(tr("已插入主窗口，当前内容已保留"))
        self._show_info(tr("已插入"), tr("结果已写入主窗口，当前手写窗口内容已保留。"))

    def _copy_result(self) -> None:
        text = self._results.text()
        if not text:
            self.status_label.setText(tr("没有可复制的内容"))
            self._show_warning(
                tr("当前无内容"), tr("请先识别或手动编辑 LaTeX 后再复制。")
            )
            return
        clipboard = QApplication.clipboard()
        if clipboard is None:
            return
        clipboard.setText(text)
        self.status_label.setText(tr("已复制 LaTeX"))
        self._show_info(tr("已复制"), tr("LaTeX 已复制到剪贴板。"))

    def is_recognizing_busy(self) -> bool:
        return self._recognition_task.busy

    def _is_owner_recognition_busy(self) -> bool:
        return self.tasks.is_busy(source="handwriting")

    def _show_busy_notice(self) -> None:
        now = time.monotonic()
        if now - self._last_busy_notice_ts < 1.5:
            return
        self._last_busy_notice_ts = now
        self._show_info(tr("正在识别"), tr("主窗口正在识别，请稍候。"))

    def _show_info(self, title: str, content: str) -> None:
        InfoBar.info(
            title=title,
            content=content,
            orient=Qt.Orientation.Vertical,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=2800,
            parent=self,
        )

    def _show_warning(self, title: str, content: str) -> None:
        InfoBar.warning(
            title=title,
            content=content,
            orient=Qt.Orientation.Vertical,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=3200,
            parent=self,
        )

    def _show_error(self, title: str, content: str) -> None:
        InfoBar.error(
            title=title,
            content=content,
            orient=Qt.Orientation.Vertical,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=4200,
            parent=self,
        )

    def closeEvent(self, event: QCloseEvent) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        self.shutdown()
        super().closeEvent(event)

    def shutdown(self) -> None:
        if self._closing:
            return
        self._closing = True
        self.recognize_timer.stop()
        self._recognition_task.shutdown()
