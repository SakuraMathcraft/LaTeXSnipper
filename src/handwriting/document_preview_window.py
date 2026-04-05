from __future__ import annotations

import shutil
import tempfile
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

from PyQt6.QtCore import QEvent, QObject, QRect, QSize, QThread, QTimer, QUrl, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QAction, QColor, QFontMetrics, QIcon, QTextFormat, QWheelEvent
from PyQt6.QtWidgets import QApplication, QFileDialog, QDialog, QHBoxLayout, QLabel, QMenu, QPlainTextEdit, QSplitter, QTextEdit, QVBoxLayout, QWidget
from qfluentwidgets import ComboBox, FluentIcon, InfoBar, InfoBarPosition, PrimaryPushButton, PushButton, isDarkTheme

from editor.latex_snippet_panel import LaTeXSnippetPanel, insert_snippet_into_editor
from editor.workbench_bridge import WorkbenchBridge
from utils import resource_path

from .tex_document_utils import WRAP_ENVIRONMENTS, validate_tex_document, wrap_tex_document

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
except Exception:  # pragma: no cover
    QWebEngineView = None

try:
    from PyQt6.QtWebChannel import QWebChannel
except Exception:  # pragma: no cover
    QWebChannel = None


class _LineNumberArea(QWidget):
    def __init__(self, editor, parent=None):
        super().__init__(parent or editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event) -> None:
        self.editor.paint_line_number_area(event)


class SlowZoomPlainTextEdit(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._line_number_area = _LineNumberArea(self)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.blockCountChanged.connect(self._update_line_number_area_width)
        self.updateRequest.connect(self._update_line_number_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self._update_line_number_area_width(0)
        self._highlight_current_line()

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta:
                self.zoomIn(1 if delta > 0 else -1)
                event.accept()
                self._update_line_number_area_width(0)
                return
        super().wheelEvent(event)

    def line_number_area_width(self) -> int:
        digits = max(2, len(str(max(1, self.blockCount()))))
        return 12 + QFontMetrics(self.font()).horizontalAdvance("9") * digits

    def _update_line_number_area_width(self, _count: int) -> None:
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_line_number_area(self, rect, dy: int) -> None:
        if dy:
            self._line_number_area.scroll(0, dy)
        else:
            self._line_number_area.update(0, rect.y(), self._line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_line_number_area_width(0)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def paint_line_number_area(self, event) -> None:
        from PyQt6.QtGui import QPainter

        painter = QPainter(self._line_number_area)
        dark = bool(isDarkTheme())
        painter.fillRect(event.rect(), QColor("#1a2029" if dark else "#f3f4f6"))
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top()))
        bottom = top + int(round(self.blockBoundingRect(block).height()))
        current_line = self.textCursor().blockNumber()
        text_color = QColor("#7f8a99" if dark else "#8b95a5")
        active_color = QColor("#d7dee8" if dark else "#334155")
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.setPen(active_color if block_number == current_line else text_color)
                painter.drawText(0, top, self._line_number_area.width() - 6, self.fontMetrics().height(), int(Qt.AlignmentFlag.AlignRight), str(block_number + 1))
            block = block.next()
            block_number += 1
            top = bottom
            bottom = top + int(round(self.blockBoundingRect(block).height()))

    def _highlight_current_line(self) -> None:
        extra = []
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            dark = bool(isDarkTheme())
            selection.format.setBackground(QColor(74, 144, 226, 92) if dark else QColor(66, 133, 244, 72))
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra.append(selection)
        self.setExtraSelections(extra)


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


class _TexDocumentCompileWorker(QObject):
    finished = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, tex_content: str, output_dir: str):
        super().__init__()
        self.tex_content = tex_content
        self.output_dir = output_dir

    def run(self) -> None:
        try:
            from backend.latex_renderer import compile_tex_document

            pdf_path, error = compile_tex_document(self.tex_content, Path(self.output_dir))
            if pdf_path is None:
                self.failed.emit(str(error or "TeX 文档编译失败"))
                return
            self.finished.emit(str(pdf_path))
        except Exception as exc:
            self.failed.emit(str(exc))


class _MathLivePreviewBridge(WorkbenchBridge):
    preferredHeightChanged = pyqtSignal(int)

    @pyqtSlot(int)
    def onMathLiveHeightChanged(self, height: int) -> None:
        try:
            value = int(height)
        except Exception:
            return
        self.preferredHeightChanged.emit(max(120, min(value, 560)))


class HandwritingDocumentPreviewWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("自动排版")
        try:
            icon_path = resource_path("assets/icon.ico")
            if icon_path:
                self.setWindowIcon(QIcon(icon_path))
        except Exception:
            pass
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )
        self.resize(920, 700)
        self._compile_thread = None
        self._compile_worker = None
        self._pdf_jump_indicator = None
        self._pdf_jump_anchor_xy = None
        self._pdf_jump_band_size = (0, 0)
        self._pdf_jump_indicator_timer = QTimer(self)
        self._pdf_jump_indicator_timer.setSingleShot(True)
        self._pdf_jump_indicator_timer.setInterval(1500)
        self._pdf_jump_indicator_timer.timeout.connect(self._hide_pdf_jump_indicator)
        self._preview_tempdir = Path(tempfile.gettempdir()) / "latexsnipper-doc-preview"
        self._preview_tempdir.mkdir(parents=True, exist_ok=True)
        self._preview_pdf_path = None
        self._pdf_backend_preference = "auto"
        self._pdf_grid_spec = "1x1"
        self._pdf_backend_kind = ""
        self._preview_area_layout = None
        self._fitz_view_cls = None
        self._poppler_view_cls = None
        self._poppler_status = self._detect_poppler_backend_light()
        self._mathlive_expand_height = 330
        self._mathlive_splitter_last_sizes = [1000, self._mathlive_expand_height]
        self._mathlive_anchor_pos = None
        self._mathlive_bridge = None
        self._mathlive_channel = None
        self._mathlive_layout_timer = QTimer(self)
        self._mathlive_layout_timer.setSingleShot(True)
        self._mathlive_layout_timer.setInterval(60)
        self._mathlive_layout_timer.timeout.connect(self._refresh_mathlive_layout)
        self._build_ui()
        self._update_compile_button_state()

    def _detect_poppler_backend_light(self):
        pdfinfo_path = shutil.which("pdfinfo") or ""
        pdftocairo_path = shutil.which("pdftocairo") or ""
        pdftoppm_path = shutil.which("pdftoppm") or ""
        ready = bool(pdfinfo_path and pdftocairo_path)
        system_found = bool(pdfinfo_path or pdftocairo_path or pdftoppm_path)
        if ready:
            detail = "已检测到 TeX Live 或 MiKTeX 提供的 Poppler 命令；当前可直接启用 Poppler 高清预览。"
        elif system_found:
            detail = "已检测到部分系统级 Poppler 命令，但缺少完整渲染链；请确认 TeX Live 或 MiKTeX 已正确安装并已加入 PATH。"
        else:
            detail = "未检测到系统级 Poppler 命令。请先部署 TeX Live 或 MiKTeX。"
        return SimpleNamespace(
            ready=ready,
            detail=detail,
            pdfinfo_path=pdfinfo_path,
            pdftocairo_path=pdftocairo_path,
            pdftoppm_path=pdftoppm_path,
        )

    def _get_fitz_view_class(self):
        if self._fitz_view_cls is None:
            try:
                mod = import_module(".pdf_view_fitz", package=__package__)
                cls = getattr(mod, "FitzPdfView", None)
            except Exception:
                cls = False
            self._fitz_view_cls = cls
        return self._fitz_view_cls if self._fitz_view_cls is not False else None

    def _get_poppler_view_class(self):
        if self._poppler_view_cls is None:
            try:
                mod = import_module(".pdf_view_poppler", package=__package__)
                cls = getattr(mod, "PopplerPdfView", None)
            except Exception:
                cls = False
            self._poppler_view_cls = cls
        return self._poppler_view_cls if self._poppler_view_cls is not False else None

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(10)
        self.preview_title_label = QLabel("自动排版", self)
        self.preview_title_label.setObjectName("docPreviewTitle")
        self.preview_hint_label = QLabel("编辑源码，按需打开公式编辑器；关闭编辑器时会自动插入到源码。", self)
        self.preview_hint_label.setObjectName("docPreviewHint")
        title_row.addWidget(self.preview_title_label)
        title_row.addWidget(self.preview_hint_label)
        title_row.addStretch(1)
        root.addLayout(title_row)

        self.preview_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.preview_splitter.setChildrenCollapsible(False)

        left = QWidget(self)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)
        self.left_splitter = QSplitter(Qt.Orientation.Vertical, left)
        self.left_splitter.setChildrenCollapsible(False)

        editor_panel = QWidget(left)
        editor_layout = QVBoxLayout(editor_panel)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(8)
        editor_layout.addWidget(QLabel("TeX 文档内容"))
        self.editor = SlowZoomPlainTextEdit(editor_panel)
        self.editor.setPlaceholderText("自动排版后的 TeX 文档会显示在这里，可直接编辑。")
        self.editor.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.editor.customContextMenuRequested.connect(self._show_editor_context_menu)
        editor_layout.addWidget(self.editor, 1)
        self.left_splitter.addWidget(editor_panel)

        control_row = QHBoxLayout()
        control_row.setContentsMargins(0, 0, 0, 0)
        control_row.setSpacing(8)
        self.snippet_panel = LaTeXSnippetPanel(left, on_insert_key=self._insert_snippet_into_editor, compact=True)
        control_row.addWidget(self.snippet_panel)
        self.mathlive_toggle_btn = PushButton(FluentIcon.EDIT, "打开编辑器", left)
        self.mathlive_toggle_btn.setFixedHeight(36)
        control_row.addWidget(self.mathlive_toggle_btn)
        self.wrap_env_combo = ComboBox(left)
        self.wrap_env_combo.setFixedHeight(32)
        self.wrap_env_combo.setMinimumWidth(154)
        for label, (env_key, _begin, _end) in WRAP_ENVIRONMENTS.items():
            self.wrap_env_combo.addItem(label, userData=env_key)
        control_row.addWidget(self.wrap_env_combo)
        self.wrap_env_btn = PushButton(FluentIcon.EMBED, "包裹选中", left)
        self.wrap_env_btn.setFixedHeight(36)
        control_row.addWidget(self.wrap_env_btn)
        control_row.addStretch(1)
        left_layout.addLayout(control_row)

        self.mathlive_panel = QWidget(left)
        self.mathlive_panel.setVisible(False)
        mathlive_panel_layout = QVBoxLayout(self.mathlive_panel)
        mathlive_panel_layout.setContentsMargins(0, 0, 0, 0)
        mathlive_panel_layout.setSpacing(8)
        if SlowZoomWebView is not None:
            self.mathlive_view = SlowZoomWebView(self.mathlive_panel)
            self.mathlive_view.setMinimumHeight(310)
            if QWebChannel is not None:
                self._mathlive_bridge = _MathLivePreviewBridge(self)
                self._mathlive_bridge.preferredHeightChanged.connect(self._on_mathlive_preferred_height_changed)
                self._mathlive_channel = QWebChannel(self.mathlive_view.page())
                self._mathlive_channel.registerObject("pyBridge", self._mathlive_bridge)
                self.mathlive_view.page().setWebChannel(self._mathlive_channel)
            self.mathlive_view.page().loadFinished.connect(self._on_mathlive_bridge_loaded)
            bridge_url = QUrl.fromLocalFile(str(Path(resource_path("assets/mathlive/bridge_panel.html")).resolve()))
            self.mathlive_view.setUrl(bridge_url)
            mathlive_panel_layout.addWidget(self.mathlive_view, 1)
        else:
            self.mathlive_view = None
            fallback = QLabel("当前环境未加载 WebEngine，无法使用 MathLive 键盘桥接层。", self.mathlive_panel)
            fallback.setWordWrap(True)
            mathlive_panel_layout.addWidget(fallback, 1)
        self.left_splitter.addWidget(self.mathlive_panel)
        self.left_splitter.setStretchFactor(0, 5)
        self.left_splitter.setStretchFactor(1, 2)
        self.left_splitter.setSizes(self._mathlive_splitter_last_sizes)
        self.left_splitter.splitterMoved.connect(self._remember_mathlive_splitter_sizes)
        left_layout.addWidget(self.left_splitter, 1)
        self._set_mathlive_panel_visible(False)
        self._sync_mathlive_bridge_buttons()
        self.preview_splitter.addWidget(left)

        right = QWidget(self)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)
        preview_header = QHBoxLayout()
        preview_header.setContentsMargins(0, 0, 0, 0)
        preview_header.setSpacing(8)
        preview_header.addWidget(QLabel("PDF 预览"))
        self.pdf_backend_status_label = QLabel("", right)
        self.pdf_backend_status_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        preview_header.addWidget(self.pdf_backend_status_label)
        preview_header.addStretch(1)
        self.pdf_backend_combo = ComboBox(right)
        self.pdf_backend_combo.setMinimumWidth(148)
        self.pdf_backend_combo.setFixedHeight(32)
        self.pdf_backend_combo.addItem("自动", userData="auto")
        self.pdf_backend_combo.addItem("Poppler(高清)", userData="poppler")
        self.pdf_backend_combo.addItem("Fitz(兼容)", userData="fitz")
        preview_header.addWidget(self.pdf_backend_combo)
        right_layout.addLayout(preview_header)
        toolbar = QHBoxLayout()
        self.actual_size_btn = PushButton(FluentIcon.ZOOM, "实际大小")
        self.fit_window_btn = PushButton(FluentIcon.FIT_PAGE, "适应窗口")
        self.fit_width_btn = PushButton(FluentIcon.VIDEO, "适应宽度")
        self.fit_text_width_btn = PushButton(FluentIcon.BOOK_SHELF, "适应文本宽度")
        self.pdf_grid_combo = ComboBox(right)
        self.pdf_grid_combo.setFixedHeight(32)
        self.pdf_grid_combo.setMinimumWidth(110)
        self.pdf_grid_combo.addItem("1x1 网格", userData="1x1")
        self.pdf_grid_combo.addItem("2x1 网格", userData="2x1")
        self.pdf_grid_combo.addItem("3x1 网格", userData="3x1")
        for btn in (self.actual_size_btn, self.fit_window_btn, self.fit_width_btn, self.fit_text_width_btn):
            btn.setFixedHeight(32)
            toolbar.addWidget(btn)
        toolbar.addWidget(self.pdf_grid_combo)
        toolbar.addStretch(1)
        right_layout.addLayout(toolbar)
        self.preview_host = QWidget(right)
        self._preview_area_layout = QVBoxLayout(self.preview_host)
        self._preview_area_layout.setContentsMargins(0, 0, 0, 0)
        self._preview_area_layout.setSpacing(0)
        self.pdf_view = None
        self.preview_placeholder = None
        right_layout.addWidget(self.preview_host, 1)
        self.preview_splitter.addWidget(right)
        self.preview_splitter.setStretchFactor(0, 5)
        self.preview_splitter.setStretchFactor(1, 4)
        self.preview_splitter.splitterMoved.connect(self._schedule_mathlive_layout_refresh)
        root.addWidget(self.preview_splitter, 1)

        btn_row = QHBoxLayout()
        self.compile_btn = PushButton(FluentIcon.PRINT, "编译预览 PDF")
        self.compile_btn.setFixedHeight(34)
        self.compile_btn.setMinimumWidth(150)
        btn_row.addWidget(self.compile_btn)
        btn_row.addStretch(1)
        self.copy_btn = PushButton(FluentIcon.COPY, "复制")
        self.export_pdf_btn = PushButton(FluentIcon.DOCUMENT, "导出 PDF")
        self.export_btn = PushButton(FluentIcon.SHARE, "导出 .tex")
        self.close_btn = PrimaryPushButton(FluentIcon.CLOSE, "关闭")
        for btn in (self.copy_btn, self.export_pdf_btn, self.export_btn, self.close_btn):
            btn.setFixedHeight(34)
        btn_row.addWidget(self.copy_btn)
        btn_row.addWidget(self.export_pdf_btn)
        btn_row.addWidget(self.export_btn)
        btn_row.addWidget(self.close_btn)
        root.addLayout(btn_row)

        self.compile_btn.clicked.connect(self._compile_preview)
        self.actual_size_btn.clicked.connect(self._set_pdf_actual_size)
        self.fit_window_btn.clicked.connect(self._set_pdf_fit_window)
        self.fit_width_btn.clicked.connect(self._set_pdf_fit_width)
        self.fit_text_width_btn.clicked.connect(self._set_pdf_fit_text_width)
        self.pdf_grid_combo.currentIndexChanged.connect(self._on_pdf_grid_changed)
        self.pdf_backend_combo.currentIndexChanged.connect(self._on_pdf_backend_changed)
        self.mathlive_toggle_btn.clicked.connect(self._toggle_mathlive_bridge)
        self.wrap_env_btn.clicked.connect(self._wrap_selected_editor_content)
        self.copy_btn.clicked.connect(self._copy_all)
        self.export_pdf_btn.clicked.connect(self._export_pdf)
        self.export_btn.clicked.connect(self._export_tex)
        self.close_btn.clicked.connect(self.close)
        self._apply_preview_theme()
        self._rebuild_pdf_backend_view(show_feedback=False)

    def set_document(self, text: str) -> None:
        wrapped = wrap_tex_document(text)
        self.editor.setPlainText(wrapped)
        begin_token = r"\begin{document}"
        begin_idx = wrapped.find(begin_token)
        if begin_idx >= 0:
            line_start = wrapped.find("\n", begin_idx + len(begin_token))
            if line_start >= 0:
                cursor = self.editor.textCursor()
                cursor.setPosition(line_start + 1)
                self.editor.setTextCursor(cursor)
                self._focus_editor_cursor()
        self._update_compile_button_state()

    def document_text(self) -> str:
        return self.editor.toPlainText().strip()

    def _insert_snippet_into_editor(self, key: str) -> None:
        insert_snippet_into_editor(self.editor, key)

    def _wrap_selected_editor_content(self) -> None:
        cursor = self.editor.textCursor()
        selected = cursor.selectedText().replace("\u2029", "\n")
        if not selected.strip():
            InfoBar.warning(title="未选择内容", content="请先在源码区选中需要包裹的内容。", parent=self, position=InfoBarPosition.TOP, duration=2200)
            return
        env_key = str(self.wrap_env_combo.currentData() or "").strip()
        begin = end = None
        for _label, (key, start_token, end_token) in WRAP_ENVIRONMENTS.items():
            if key == env_key:
                begin, end = start_token, end_token
                break
        if not begin or not end:
            return
        stripped = selected.strip()
        wrapped = f"{begin}{stripped}{end}" if env_key == "inline" else f"{begin}\n{stripped}\n{end}"
        cursor.insertText(wrapped)
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()
        InfoBar.success(title="已包裹选中内容", content=f"已包裹为 {env_key}", parent=self, position=InfoBarPosition.TOP, duration=1800)

    def _set_mathlive_panel_visible(self, visible: bool) -> None:
        actual_visible = bool(visible and self.mathlive_view is not None)
        if actual_visible:
            self.mathlive_panel.setVisible(True)
            total = max(1, self.left_splitter.height())
            lower = max(180, min(self._mathlive_expand_height, max(180, total // 2)))
            upper = max(220, total - lower)
            sizes = self._mathlive_splitter_last_sizes if sum(self._mathlive_splitter_last_sizes) > 0 else [upper, lower]
            self.left_splitter.setSizes(sizes)
            self._schedule_mathlive_layout_refresh()
        else:
            try:
                sizes = self.left_splitter.sizes()
                if len(sizes) >= 2 and sizes[1] > 0:
                    self._mathlive_splitter_last_sizes = sizes[:2]
            except Exception:
                pass
            total = max(1, sum(self.left_splitter.sizes()) or self.left_splitter.height() or 1)
            self.left_splitter.setSizes([total, 0])
            self.mathlive_panel.setVisible(False)
        self._sync_mathlive_bridge_buttons()

    def _remember_mathlive_splitter_sizes(self, *_args) -> None:
        if not self.mathlive_panel.isVisible():
            return
        try:
            sizes = self.left_splitter.sizes()
        except Exception:
            return
        if len(sizes) >= 2 and sizes[1] > 0:
            self._mathlive_splitter_last_sizes = sizes[:2]
            self._mathlive_expand_height = sizes[1]
        self._schedule_mathlive_layout_refresh()

    def _sync_mathlive_bridge_buttons(self) -> None:
        has_bridge = self.mathlive_view is not None
        self.mathlive_toggle_btn.setEnabled(has_bridge)
        is_open = bool(has_bridge and self.mathlive_panel.isVisible() and self.left_splitter.sizes()[1] > 0)
        self.mathlive_toggle_btn.setText("关闭编辑器" if is_open else "打开编辑器")
        self.mathlive_toggle_btn.setToolTip("打开 MathLive 编辑器；关闭时会自动插入到源码" if has_bridge else "当前环境未加载 WebEngine，MathLive 键盘桥接层不可用")

    def _toggle_mathlive_bridge(self) -> None:
        if self.mathlive_view is None:
            return
        visible = not self.mathlive_panel.isVisible() or self.left_splitter.sizes()[1] == 0
        if visible:
            self._mathlive_anchor_pos = self.editor.textCursor().position()
            self._set_mathlive_panel_visible(True)
            self._focus_mathlive_bridge(show_keyboard=True)
        else:
            self._set_mathlive_panel_visible(False)
            QTimer.singleShot(200, self._commit_mathlive_into_editor)

    def _on_mathlive_bridge_loaded(self, ok: bool) -> None:
        if ok:
            self._apply_mathlive_bridge_theme()

    def _apply_mathlive_bridge_theme(self) -> None:
        if self.mathlive_view is None:
            return
        mode = "dark" if isDarkTheme() else "light"
        self.mathlive_view.page().runJavaScript(f"window.mathliveBridgeApi?.setThemeMode('{mode}')")
        self._schedule_mathlive_layout_refresh()

    def _focus_mathlive_bridge(self, show_keyboard: bool = True) -> None:
        if self.mathlive_view is None:
            return
        script = f"window.mathliveBridgeApi?.focusMathfield({'true' if show_keyboard else 'false'})"
        try:
            self.mathlive_view.setFocus(Qt.FocusReason.OtherFocusReason)
            self.mathlive_view.activateWindow()
        except Exception:
            pass
        self.mathlive_view.page().runJavaScript(script)
        QTimer.singleShot(0, lambda: self.mathlive_view.page().runJavaScript(script))
        QTimer.singleShot(180, lambda: self.mathlive_view.page().runJavaScript(script))

    def _schedule_mathlive_layout_refresh(self, *_args) -> None:
        if self.mathlive_view is None or not self.mathlive_panel.isVisible():
            return
        self._mathlive_layout_timer.start()

    def _refresh_mathlive_layout(self) -> None:
        if self.mathlive_view is None or not self.mathlive_panel.isVisible():
            return
        self.mathlive_view.page().runJavaScript("window.mathliveBridgeApi?.syncLayout?.()")

    def _on_mathlive_preferred_height_changed(self, height: int) -> None:
        target = max(120, min(int(height), 560))
        self._mathlive_expand_height = target
        if self.mathlive_view is None or not self.mathlive_panel.isVisible():
            return
        self.mathlive_view.setMinimumHeight(max(100, target - 12))
        self.mathlive_view.updateGeometry()
        self.mathlive_panel.updateGeometry()
        try:
            sizes = self.left_splitter.sizes()
        except Exception:
            return
        if len(sizes) >= 2 and sizes[1] < target:
            total = max(sum(sizes), self.left_splitter.height(), target + 220)
            upper = max(220, total - target)
            self.left_splitter.setSizes([upper, target])
            self._mathlive_splitter_last_sizes = [upper, target]

    def _focus_editor_cursor(self) -> None:
        self.editor.ensureCursorVisible()
        try:
            self.editor.centerCursor()
        except Exception:
            pass

    def _show_editor_context_menu(self, pos) -> None:
        cursor = self.editor.cursorForPosition(pos)
        line_no = int(cursor.blockNumber()) + 1
        menu = QMenu(self.editor)
        cut_action = QAction("剪切", menu)
        copy_action = QAction("复制", menu)
        paste_action = QAction("粘贴", menu)
        jump_action = QAction("跳转到 PDF", menu)
        cut_action.setEnabled(self.editor.textCursor().hasSelection() and not self.editor.isReadOnly())
        copy_action.setEnabled(self.editor.textCursor().hasSelection())
        paste_action.setEnabled((not self.editor.isReadOnly()) and bool(QApplication.clipboard().text()))
        menu.addAction(cut_action)
        menu.addAction(copy_action)
        menu.addAction(paste_action)
        menu.addSeparator()
        menu.addAction(jump_action)
        chosen = menu.exec(self.editor.mapToGlobal(pos))
        if chosen is cut_action:
            self.editor.cut()
            return
        if chosen is copy_action:
            self.editor.copy()
            return
        if chosen is paste_action:
            self.editor.paste()
            return
        if chosen is jump_action:
            self.editor.setTextCursor(cursor)
            self._jump_to_pdf_from_source_line(line_no)

    def _jump_to_pdf_from_source_line(self, line_no: int) -> None:
        pdf_path = Path(self._preview_pdf_path) if self._preview_pdf_path else None
        if pdf_path is None or not pdf_path.exists():
            InfoBar.warning(title="无法跳转", content="请先完成一次 PDF 编译预览。", parent=self, position=InfoBarPosition.TOP, duration=2500)
            return
        source_path = Path(self._preview_tempdir) / "document_preview.tex"
        if not source_path.exists():
            InfoBar.warning(title="无法跳转", content="未找到编译时源码，请先重新编译。", parent=self, position=InfoBarPosition.TOP, duration=2500)
            return
        try:
            from backend.latex_renderer import synctex_view_from_source

            page, x_pt, y_pt, w_pt, h_pt, error = synctex_view_from_source(source_file=source_path, line_no=int(line_no), pdf_file=pdf_path)
        except Exception as exc:
            page, x_pt, y_pt, w_pt, h_pt, error = None, None, None, None, None, str(exc)
        if error:
            InfoBar.warning(title="SyncTeX 跳转失败", content=str(error), parent=self, position=InfoBarPosition.TOP, duration=3200)
            return
        if page is None or x_pt is None or y_pt is None:
            InfoBar.warning(title="未定位到 PDF", content="SyncTeX 未返回有效的 PDF 坐标。", parent=self, position=InfoBarPosition.TOP, duration=2500)
            return
        if not self._scroll_pdf_to_point(int(page), float(x_pt), float(y_pt), width_pt=w_pt, height_pt=h_pt):
            InfoBar.warning(title="跳转未完成", content="当前预览控件不支持定位到 PDF 坐标。", parent=self, position=InfoBarPosition.TOP, duration=2500)
            return
        InfoBar.success(title="已跳转到 PDF", content=f"源码第 {int(line_no)} 行", parent=self, position=InfoBarPosition.TOP, duration=1600)

    def _scroll_pdf_to_point(self, page: int, x_pt: float, y_pt: float, width_pt: float | None = None, height_pt: float | None = None) -> bool:
        view = self.pdf_view
        if view is None:
            return False
        if not hasattr(view, "_page_rects") or not hasattr(view, "_page_sizes"):
            return False
        page_rects = getattr(view, "_page_rects", None) or []
        page_sizes = getattr(view, "_page_sizes", None) or []
        # In packaged builds, rendering/layout can be slightly behind after compile.
        # Retry one layout pass before failing the jump.
        if not page_rects or not page_sizes:
            refreshed = False
            for fn_name in ("_layout_pages", "_render_pages"):
                fn = getattr(view, fn_name, None)
                if callable(fn):
                    try:
                        fn()
                        refreshed = True
                        break
                    except Exception:
                        pass
            if refreshed:
                page_rects = getattr(view, "_page_rects", None) or []
                page_sizes = getattr(view, "_page_sizes", None) or []
        idx = max(0, int(page) - 1)
        if idx >= len(page_rects) or idx >= len(page_sizes):
            return False
        rect = page_rects[idx]
        page_w, page_h = page_sizes[idx]
        if float(page_w) <= 1e-6 or float(page_h) <= 1e-6:
            return False
        rel_x = max(0.0, min(1.0, float(x_pt) / float(page_w)))
        rel_y = max(0.0, min(1.0, float(y_pt) / float(page_h)))
        target_x = int(round(float(rect.x()) + rel_x * float(rect.width())))
        target_y = int(round(float(rect.y()) + rel_y * float(rect.height())))
        scale_x = float(rect.width()) / max(1e-6, float(page_w))
        scale_y = float(rect.height()) / max(1e-6, float(page_h))
        width_px = max(0, int(round(float(width_pt) * scale_x))) if width_pt is not None else 0
        height_px = max(0, int(round(float(height_pt) * scale_y))) if height_pt is not None else 0
        try:
            hbar = view.horizontalScrollBar()
            vbar = view.verticalScrollBar()
            vp = view.viewport() if hasattr(view, "viewport") else None
            half_w = int(vp.width() // 2) if vp is not None else 0
            half_h = int(vp.height() // 2) if vp is not None else 0
            hbar.setValue(max(0, target_x - half_w))
            vbar.setValue(max(0, target_y - half_h))
            if vp is not None:
                self._show_pdf_jump_indicator(target_x, target_y, line_width_px=width_px, line_height_px=height_px)
            return True
        except Exception:
            return False

    def _show_pdf_jump_indicator(self, x: int, y: int, line_width_px: int = 0, line_height_px: int = 0) -> None:
        view = self.pdf_view
        if view is None or not hasattr(view, "viewport"):
            return
        vp = view.viewport()
        if vp is None:
            return
        marker = self._pdf_jump_indicator
        if marker is not None:
            try:
                marker.parentWidget()
            except RuntimeError:
                marker = None
                self._pdf_jump_indicator = None
        if marker is None:
            marker = QWidget(vp)
            marker.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            marker.setStyleSheet(
                """
                background: rgba(88, 166, 255, 78);
                border: none;
                border-radius: 0px;
                """
            )
            marker.hide()
            self._pdf_jump_indicator = marker
        raw_h = int(round(float(line_height_px) * 0.68)) if line_height_px > 0 else 14
        band_h = max(8, min(18, raw_h))
        band_w = max(42, line_width_px if line_width_px > 0 else int(vp.width() * 0.55))
        right_trim = max(1, int(round(float(band_h) * 0.10)))
        band_w = max(24, int(band_w - right_trim))
        self._pdf_jump_anchor_xy = (int(x), int(y))
        self._pdf_jump_band_size = (int(band_w), int(band_h))
        marker.resize(band_w, band_h)
        self._refresh_pdf_jump_indicator_position()
        marker.show()
        marker.raise_()
        self._pdf_jump_indicator_timer.start()

    def _refresh_pdf_jump_indicator_position(self, *_args) -> None:
        marker = self._pdf_jump_indicator
        view = self.pdf_view
        if marker is None or view is None or self._pdf_jump_anchor_xy is None:
            return
        if not hasattr(view, "viewport"):
            return
        vp = view.viewport()
        if vp is None:
            return
        try:
            hbar = view.horizontalScrollBar()
            vbar = view.verticalScrollBar()
            anchor_x, anchor_y = self._pdf_jump_anchor_xy
            band_w, band_h = self._pdf_jump_band_size
            view_x = int(anchor_x - hbar.value())
            view_y = int(anchor_y - vbar.value())
            # SyncTeX x anchor tends to drift right by about one glyph on some fonts.
            left_pad = max(6, int(round(float(band_h) * 0.78)))
            left = int(view_x - left_pad)
            top = int(view_y - int(round(float(band_h) * 0.65)))
            left = max(0, min(left, int(vp.width() - band_w)))
            top = max(0, min(top, int(vp.height() - band_h)))
            marker.move(left, top)
        except Exception:
            return

    def _hide_pdf_jump_indicator(self) -> None:
        marker = self._pdf_jump_indicator
        if marker is not None:
            try:
                marker.hide()
            except RuntimeError:
                self._pdf_jump_indicator = None
        self._pdf_jump_anchor_xy = None

    def _commit_mathlive_into_editor(self) -> None:
        if self.mathlive_view is None:
            self._mathlive_anchor_pos = None
            return
        self.mathlive_view.page().runJavaScript("window.mathliveBridgeApi?.currentLatex() || ''", self._apply_mathlive_commit)

    def _apply_mathlive_commit(self, result) -> None:
        latex = str(result or "").strip()
        anchor = self._mathlive_anchor_pos
        if latex and anchor is not None:
            cursor = self.editor.textCursor()
            cursor.setPosition(int(anchor))
            cursor.insertText(latex)
            self.editor.setTextCursor(cursor)
            self.editor.setFocus()
            self.mathlive_view.page().runJavaScript("window.mathliveBridgeApi?.clearMathfield?.()")
        self._focus_editor_cursor()
        self._mathlive_anchor_pos = None

    def _set_pdf_actual_size(self) -> None:
        if self.pdf_view is not None:
            self.pdf_view.set_actual_size()

    def _set_pdf_fit_window(self) -> None:
        if self.pdf_view is not None:
            self.pdf_view.set_fit_window()

    def _set_pdf_fit_width(self) -> None:
        if self.pdf_view is not None:
            self.pdf_view.set_fit_width()

    def _set_pdf_fit_text_width(self) -> None:
        if self.pdf_view is not None:
            self.pdf_view.set_fit_text_width()

    def _desired_pdf_backend(self) -> str:
        return str(self.pdf_backend_combo.currentData() or self._pdf_backend_preference or "auto").strip()

    def _resolve_pdf_backend_kind(self) -> str:
        self._poppler_status = self._detect_poppler_backend_light()
        preferred = self._desired_pdf_backend()
        fitz_cls = self._get_fitz_view_class()
        if preferred == "poppler":
            if self._poppler_status.ready:
                return "poppler"
            return "fitz" if fitz_cls is not None else ""
        if preferred == "fitz":
            if fitz_cls is not None:
                return "fitz"
        if self._poppler_status.ready:
            return "poppler"
        if fitz_cls is not None:
            return "fitz"
        return ""

    def _clear_preview_host(self) -> None:
        self._pdf_jump_indicator_timer.stop()
        marker = self._pdf_jump_indicator
        self._pdf_jump_indicator = None
        self._pdf_jump_anchor_xy = None
        self._pdf_jump_band_size = (0, 0)
        if marker is not None:
            try:
                marker.deleteLater()
            except Exception:
                pass
        if self.pdf_view is not None:
            try:
                try:
                    self.pdf_view.horizontalScrollBar().valueChanged.disconnect(self._refresh_pdf_jump_indicator_position)
                except Exception:
                    pass
                try:
                    self.pdf_view.verticalScrollBar().valueChanged.disconnect(self._refresh_pdf_jump_indicator_position)
                except Exception:
                    pass
                if self._pdf_backend_kind == "poppler" and hasattr(self.pdf_view, "shutdown_render_worker"):
                    self.pdf_view.shutdown_render_worker()
                self.pdf_view.close()
                self.pdf_view.setParent(None)
                self.pdf_view.deleteLater()
            except Exception:
                pass
        self.pdf_view = None
        self._pdf_jump_anchor_xy = None
        if self.preview_placeholder is not None:
            try:
                self.preview_placeholder.setParent(None)
                self.preview_placeholder.deleteLater()
            except Exception:
                pass
        self.preview_placeholder = None

    def _parse_pdf_grid_spec(self) -> tuple[int, int]:
        text = str(self._pdf_grid_spec or "1x1").strip().lower()
        if "x" not in text:
            return 1, 1
        parts = text.split("x", 1)
        try:
            cols = max(1, int(parts[0]))
        except Exception:
            cols = 1
        try:
            rows = max(1, int(parts[1]))
        except Exception:
            rows = 1
        return cols, rows

    def _apply_pdf_grid_to_view(self) -> None:
        if self.pdf_view is None:
            return
        cols, rows = self._parse_pdf_grid_spec()
        if hasattr(self.pdf_view, "set_page_grid"):
            try:
                self.pdf_view.set_page_grid(cols, rows)
            except Exception:
                pass

    def _create_pdf_view_for_kind(self, kind: str):
        if kind == "poppler":
            poppler_cls = self._get_poppler_view_class()
            if poppler_cls is not None:
                return poppler_cls(self.preview_host)
            return None
        if kind == "fitz":
            fitz_cls = self._get_fitz_view_class()
            if fitz_cls is not None:
                return fitz_cls(self.preview_host)
        return None

    def _set_pdf_backend_status_text(self, text: str) -> None:
        if hasattr(self, "pdf_backend_status_label"):
            self.pdf_backend_status_label.setText(text)

    def _describe_active_pdf_backend(self, requested: str, actual: str) -> str:
        if actual == "poppler":
            return "当前后端: Poppler(高清)"
        if actual == "fitz":
            if requested == "poppler":
                return "当前后端: Fitz(兼容，Poppler 未启用)"
            return "当前后端: Fitz(兼容)"
        if requested == "poppler":
            return "当前后端: Poppler 不可用"
        return "当前后端: 无可用预览后端"

    def _rebuild_pdf_backend_view(self, show_feedback: bool = True) -> None:
        kind = self._resolve_pdf_backend_kind()
        requested = self._desired_pdf_backend()
        if kind == self._pdf_backend_kind and self.pdf_view is not None:
            self._set_pdf_backend_status_text(self._describe_active_pdf_backend(requested, kind))
            if show_feedback and requested == "poppler":
                self._show_poppler_backend_info()
            return
        self._clear_preview_host()
        self._pdf_backend_kind = kind
        self._set_pdf_backend_status_text(self._describe_active_pdf_backend(requested, kind))
        if kind:
            self.pdf_view = self._create_pdf_view_for_kind(kind)
            if self.pdf_view is not None:
                self.pdf_view.syncJumpRequested.connect(self._sync_jump_to_source)
                try:
                    self.pdf_view.horizontalScrollBar().valueChanged.connect(self._refresh_pdf_jump_indicator_position)
                    self.pdf_view.verticalScrollBar().valueChanged.connect(self._refresh_pdf_jump_indicator_position)
                except Exception:
                    pass
                self._preview_area_layout.addWidget(self.pdf_view, 1)
                if self._preview_pdf_path:
                    try:
                        self.pdf_view.load_document(self._preview_pdf_path)
                    except Exception:
                        pass
                self._apply_pdf_grid_to_view()
                if show_feedback and requested == "poppler":
                    self._show_poppler_backend_info()
                return
        self.preview_placeholder = QLabel("当前环境缺少可用的 PDF 预览引擎。", self.preview_host)
        self.preview_placeholder.setWordWrap(True)
        self.preview_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_area_layout.addWidget(self.preview_placeholder, 1)

    def _on_pdf_backend_changed(self) -> None:
        self._pdf_backend_preference = self._desired_pdf_backend()
        self._rebuild_pdf_backend_view(show_feedback=True)

    def _on_pdf_grid_changed(self) -> None:
        self._pdf_grid_spec = str(self.pdf_grid_combo.currentData() or "1x1")
        self._apply_pdf_grid_to_view()

    def _show_poppler_backend_info(self) -> None:
        self._poppler_status = self._detect_poppler_backend_light()
        if self._poppler_status.ready:
            title = "已切换到 Poppler(高清)"
            content = "当前 PDF 预览使用 Poppler 渲染。"
            duration = 1800
        else:
            title = "Poppler 未启用"
            content = "当前环境缺少可用的 Poppler 命令，已回退到 Fitz(兼容)。"
            duration = 2600
        InfoBar.info(title=title, content=content, parent=self, position=InfoBarPosition.TOP, duration=duration)

    def showEvent(self, event) -> None:
        self._update_compile_button_state()
        self._apply_mathlive_bridge_theme()
        self._apply_preview_theme()
        super().showEvent(event)
        self._schedule_mathlive_layout_refresh()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._schedule_mathlive_layout_refresh()

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        self._apply_preview_theme()

    def _apply_preview_theme(self) -> None:
        dark = bool(isDarkTheme())
        title = "#eef2f7" if dark else "#16202a"
        hint = "#a9b4c3" if dark else "#6b7787"
        if hasattr(self, "preview_title_label"):
            self.preview_title_label.setStyleSheet(f"color: {title}; font-size: 24px; font-weight: 600;")
        if hasattr(self, "preview_hint_label"):
            self.preview_hint_label.setStyleSheet(f"color: {hint}; font-size: 12px; padding-top: 6px;")
        if hasattr(self, "pdf_backend_status_label"):
            self.pdf_backend_status_label.setStyleSheet(f"color: {hint}; font-size: 12px;")

    def _copy_all(self) -> None:
        text = self.document_text()
        if not text:
            InfoBar.warning(title="当前无内容", content="没有可复制的 TeX 文档。", parent=self, position=InfoBarPosition.TOP, duration=2500)
            return
        QApplication.clipboard().setText(text)
        InfoBar.success(title="已复制", content="TeX 文档已复制到剪贴板。", parent=self, position=InfoBarPosition.TOP, duration=2500)

    def _export_tex(self) -> None:
        text = self.document_text()
        if not text:
            InfoBar.warning(title="当前无内容", content="没有可导出的 TeX 文档。", parent=self, position=InfoBarPosition.TOP, duration=2500)
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出 TeX 文档", "handwriting_layout.tex", "TeX 文档 (*.tex)")
        if not path:
            return
        try:
            Path(path).write_text(text, encoding="utf-8")
        except Exception as exc:
            InfoBar.error(title="导出失败", content=str(exc), parent=self, position=InfoBarPosition.TOP, duration=3200)
            return
        InfoBar.success(title="导出成功", content=Path(path).name, parent=self, position=InfoBarPosition.TOP, duration=2500)

    def _export_pdf(self) -> None:
        pdf_path = Path(self._preview_pdf_path) if self._preview_pdf_path else None
        if pdf_path is None or not pdf_path.exists():
            InfoBar.warning(title="当前无 PDF", content="请先完成一次 PDF 编译预览后再导出。", parent=self, position=InfoBarPosition.TOP, duration=2500)
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出 PDF", "handwriting_layout.pdf", "PDF 文件 (*.pdf)")
        if not path:
            return
        try:
            shutil.copy2(pdf_path, path)
        except Exception as exc:
            InfoBar.error(title="导出失败", content=str(exc), parent=self, position=InfoBarPosition.TOP, duration=3200)
            return
        InfoBar.success(title="导出成功", content=Path(path).name, parent=self, position=InfoBarPosition.TOP, duration=2500)

    def _sync_jump_to_source(self, page: int, x_pt: float, y_pt: float) -> None:
        pdf_path = Path(self._preview_pdf_path) if self._preview_pdf_path else None
        if pdf_path is None or not pdf_path.exists():
            InfoBar.warning(title="无法跳转", content="请先完成一次 PDF 编译预览后再使用源码跳转。", parent=self, position=InfoBarPosition.TOP, duration=2500)
            return
        try:
            from backend.latex_renderer import synctex_edit_from_pdf

            source, line_no, error = synctex_edit_from_pdf(pdf_file=pdf_path, page=page, x_pt=x_pt, y_pt=y_pt)
        except Exception as exc:
            source, line_no, error = None, None, str(exc)
        if error:
            InfoBar.warning(title="SyncTeX 跳转失败", content=str(error), parent=self, position=InfoBarPosition.TOP, duration=3200)
            return
        if not line_no or line_no <= 0:
            InfoBar.warning(title="未定位到源码", content="SyncTeX 未返回有效的源码行号。", parent=self, position=InfoBarPosition.TOP, duration=2500)
            return
        block = self.editor.document().findBlockByLineNumber(max(0, int(line_no) - 1))
        if not block.isValid():
            InfoBar.warning(title="未定位到源码", content=f"已解析到第 {line_no} 行，但当前编辑器中未找到对应位置。", parent=self, position=InfoBarPosition.TOP, duration=2500)
            return
        cursor = self.editor.textCursor()
        cursor.setPosition(block.position())
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()
        self._focus_editor_cursor()
        origin = source.name if isinstance(source, Path) else "当前源码"
        InfoBar.success(title="已跳转到源码", content=f"{origin} 第 {line_no} 行", parent=self, position=InfoBarPosition.TOP, duration=1800)

    def _prepare_preview_output_dir(self) -> None:
        output_dir = Path(self._preview_tempdir)
        output_dir.mkdir(parents=True, exist_ok=True)
        for candidate in output_dir.glob("document_preview.*"):
            try:
                if candidate.is_dir():
                    shutil.rmtree(candidate, ignore_errors=True)
                else:
                    candidate.unlink()
            except Exception:
                pass

    def _current_render_mode(self) -> str:
        try:
            from backend.latex_renderer import get_document_render_mode

            return get_document_render_mode()
        except Exception:
            return "auto"

    def _update_compile_button_state(self) -> None:
        if self._compile_thread is not None and self._compile_thread.isRunning():
            self.compile_btn.setEnabled(False)
            self.compile_btn.setText("编译中...")
            return
        self.compile_btn.setEnabled(True)
        self.compile_btn.setText("编译预览 PDF")

    def _compile_preview(self) -> None:
        self._update_compile_button_state()
        mode = self._current_render_mode()
        if mode not in {"latex_pdflatex", "latex_xelatex"}:
            InfoBar.info(title="暂不可用", content="请先在设置中选择 LaTeX + pdflatex 或 LaTeX + xelatex。", parent=self, position=InfoBarPosition.TOP, duration=3200)
            return
        if self._compile_thread is not None and self._compile_thread.isRunning():
            InfoBar.info(title="正在编译", content="当前文档正在编译，请稍候。", parent=self, position=InfoBarPosition.TOP, duration=2500)
            return
        compile_text = self.document_text()
        validation_error = validate_tex_document(compile_text)
        if validation_error:
            InfoBar.warning(title="文档未完成", content=validation_error, parent=self, position=InfoBarPosition.TOP, duration=3200)
            return
        self._prepare_preview_output_dir()
        self._preview_pdf_path = None
        self.compile_btn.setText("编译中...")
        self.compile_btn.setEnabled(False)
        self._compile_thread = QThread(self)
        self._compile_worker = _TexDocumentCompileWorker(compile_text, str(self._preview_tempdir))
        worker = self._compile_worker
        thread = self._compile_thread
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_compile_finished)
        worker.failed.connect(self._on_compile_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._teardown_compile)
        thread.start()

    def _teardown_compile(self) -> None:
        self._compile_worker = None
        self._compile_thread = None
        self._update_compile_button_state()

    def _on_compile_finished(self, pdf_path: str) -> None:
        self._preview_pdf_path = str(pdf_path)
        if self.pdf_view is not None:
            self.pdf_view.load_document(self._preview_pdf_path)
        elif self.preview_placeholder is not None:
            self.preview_placeholder.setText(f"PDF 已生成: {self._preview_pdf_path}")
        InfoBar.success(title="编译完成", content="PDF 预览已更新。", parent=self, position=InfoBarPosition.TOP, duration=2500)

    def _on_compile_failed(self, error: str) -> None:
        InfoBar.error(title="编译失败", content=str(error or "TeX 文档编译失败"), parent=self, position=InfoBarPosition.TOP, duration=4200)

    def closeEvent(self, event) -> None:
        self._mathlive_anchor_pos = None
        self._mathlive_layout_timer.stop()
        self._pdf_jump_indicator_timer.stop()
        try:
            self._clear_preview_host()
        except Exception:
            pass
        thread = self._compile_thread
        if thread is not None:
            try:
                thread.requestInterruption()
            except Exception:
                pass
            try:
                thread.quit()
                thread.wait(150)
            except Exception:
                pass
        super().closeEvent(event)
