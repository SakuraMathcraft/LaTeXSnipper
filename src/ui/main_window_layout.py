"""Construct main-window widgets without initializing application state."""

import logging
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget
from qfluentwidgets import FluentIcon, PushButton
from localization.manager import translate as tr
from preview.math_preview import build_math_html, get_mathjax_base_url
from runtime.webengine_runtime import ensure_webengine_loaded, get_webengine_view_class
from ui.controllers.file_drop import image_extensions

logger = logging.getLogger(f"latexsnipper.{__name__}")
DEFAULT_MAIN_WINDOW_SIZE = (1180, 720)
EDITOR_TOOLBAR_RIGHT_MARGIN = 8


def build_main_window_layout(view, cfg):
    view.status_label = QLabel()
    left_panel = QWidget()
    left_layout = QVBoxLayout(left_panel)
    left_layout.setContentsMargins(6, 6, 6, 6)
    left_layout.setSpacing(8)
    view.capture_button = PushButton(FluentIcon.SEARCH, tr("截图识别"))
    view.capture_button.setFixedHeight(40)
    capture_row = QHBoxLayout()
    capture_row.addWidget(view.capture_button, 1)
    view.onboarding_button = PushButton(FluentIcon.HELP, tr("快速入门"))
    view.onboarding_button.setFixedHeight(40)
    view.onboarding_button.setToolTip(tr("查看快速入门"))
    capture_row.addWidget(view.onboarding_button)
    left_layout.addLayout(capture_row)
    history_header = QHBoxLayout()
    history_header.setContentsMargins(0, 0, 0, 0)
    history_header.setSpacing(6)
    view.history_title_label = QLabel(tr("历史记录"))
    history_header.addWidget(view.history_title_label)
    history_header.addStretch()
    view.history_order_button = PushButton(
        tr("最新在前") if bool(cfg.get("history_reverse", True)) else tr("最早在前")
    )
    view.history_order_button.setFixedHeight(28)
    history_header.addWidget(view.history_order_button)
    left_layout.addLayout(history_header)
    view.history_scroll = QScrollArea()
    view.history_scroll.setWidgetResizable(True)
    view.history_scroll.setHorizontalScrollBarPolicy(
        Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )
    view.history_container = QWidget()
    view.history_layout = QVBoxLayout(view.history_container)
    view.history_layout.setContentsMargins(0, 0, 0, 0)
    view.history_layout.setSpacing(6)
    view.history_layout.addStretch()
    view.history_scroll.setWidget(view.history_container)
    left_layout.addWidget(view.history_scroll, 1)
    btn_row = QHBoxLayout()
    view.clear_history_button = PushButton(FluentIcon.DELETE, tr("清空"))
    view.change_key_button = PushButton(FluentIcon.CLIPPING_TOOL, tr("快捷键"))
    view.show_fav_button = PushButton(FluentIcon.HEART, tr("收藏夹"))
    view.settings_button = PushButton(FluentIcon.SETTING, tr("设置"))
    btn_row.addWidget(view.clear_history_button)
    btn_row.addWidget(view.change_key_button)
    btn_row.addWidget(view.show_fav_button)
    btn_row.addWidget(view.settings_button)
    left_layout.addLayout(btn_row)
    left_layout.addWidget(view.status_label)
    right_panel = QWidget()
    right_layout = QVBoxLayout(right_panel)
    right_layout.setContentsMargins(6, 6, 6, 6)
    right_layout.setSpacing(8)
    editor_header = QHBoxLayout()
    editor_header.setContentsMargins(0, 0, 0, 0)
    editor_header.setSpacing(0)
    view.editor_title_label = QLabel(tr("LaTeX 编辑器"))
    editor_header.addWidget(view.editor_title_label)
    editor_header.addSpacing(6)
    view.upload_image_btn = PushButton(FluentIcon.PHOTO, tr("图片识别"))
    view.upload_pdf_btn = PushButton(FluentIcon.DOCUMENT, tr("PDF 识别"))
    try:
        img_exts = image_extensions()
        view.upload_image_btn.setToolTip(tr("支持格式: ") + ", ".join(img_exts))
    except Exception:
        pass
    view.upload_pdf_btn.setToolTip(tr("支持格式: PDF"))
    view.copy_editor_btn = PushButton(FluentIcon.COPY, tr("复制"))
    view.export_btn = PushButton(FluentIcon.SHARE, tr("导出"))
    view.handwriting_btn = PushButton(FluentIcon.FINGERPRINT, tr("手写识别"))
    view.workbench_btn = PushButton(FluentIcon.PROJECTOR, tr("数学工作台"))
    editor_actions = QHBoxLayout()
    editor_actions.setContentsMargins(0, 0, 0, 0)
    editor_actions.setSpacing(6)
    editor_actions.addWidget(view.upload_image_btn)
    editor_actions.addWidget(view.upload_pdf_btn)
    editor_actions.addWidget(view.handwriting_btn)
    editor_actions.addWidget(view.copy_editor_btn)
    editor_actions.addWidget(view.export_btn)
    editor_actions.addWidget(view.workbench_btn)
    editor_header.addLayout(editor_actions)
    right_layout.addLayout(editor_header)
    from qfluentwidgets import PlainTextEdit

    view.latex_editor = PlainTextEdit()
    view.latex_editor.setPlaceholderText(tr("在此输入 LaTeX 公式，下方将实时渲染..."))
    view.latex_editor.setMinimumHeight(100)
    view.latex_editor.setMaximumHeight(150)
    right_layout.addWidget(view.latex_editor)
    preview_header = QHBoxLayout()
    view.preview_title_label = QLabel(tr("实时渲染预览"))
    preview_header.addWidget(view.preview_title_label)
    preview_header.addStretch()
    view.clear_preview_btn = PushButton(FluentIcon.BROOM, tr("清空预览"))
    preview_header.addWidget(view.clear_preview_btn)
    right_layout.addLayout(preview_header)
    view.preview_fallback_label = None
    view.preview_view = None
    view._pending_latex = ""
    webengine_view_cls = (
        get_webengine_view_class() if ensure_webengine_loaded() else None
    )
    if webengine_view_cls is not None:
        view.preview_view = webengine_view_cls()
        try:
            from PyQt6.QtWebEngineCore import QWebEngineSettings

            settings = view.preview_view.settings()
            settings.setAttribute(
                QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
            )
            settings.setAttribute(
                QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True
            )
        except Exception:
            pass
        view.preview_view.setMinimumHeight(200)
        try:
            view.preview_view.setContextMenuPolicy(
                Qt.ContextMenuPolicy.DefaultContextMenu
            )
        except Exception:
            pass
        try:
            pg = view.preview_view.page()
            pg.renderProcessTerminated.connect(
                lambda status, code: logger.warning(
                    "WebEngine 渲染进程终止 status=%s code=%s", status, code
                )
            )
        except Exception:
            pass
        html = build_math_html("")
        base_url = get_mathjax_base_url()
        try:
            view.preview_view.setHtml(html, base_url)
        except Exception:
            pass
        right_layout.addWidget(view.preview_view, 1)
        pass
    else:
        view.preview_fallback_label = QLabel(
            tr("WebEngine 未加载，无法渲染公式预览。\n请确保已安装 PyQtWebEngine。")
        )
        view.preview_fallback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_layout.addWidget(view.preview_fallback_label, 1)
    from PyQt6.QtWidgets import QSplitter

    splitter = QSplitter(Qt.Orientation.Horizontal)
    splitter.addWidget(left_panel)
    splitter.addWidget(right_panel)
    splitter.setSizes([420, 900])
    splitter.setCollapsible(0, False)
    splitter.setCollapsible(1, False)
    container = QWidget()
    main_layout = QVBoxLayout(container)
    main_layout.setContentsMargins(0, 0, 0, 0)
    main_layout.addWidget(splitter)
    view.setCentralWidget(container)
    view.size_layouts = (
        left_layout,
        editor_header,
        preview_header,
        right_layout,
        left_panel,
        splitter,
    )
    view.drop_targets = (
        left_panel,
        right_panel,
        splitter,
        container,
        view.latex_editor,
        view.latex_editor.viewport(),
        view.preview_view,
        view.preview_fallback_label,
    )


def adjust_main_window_size(view):
    left_layout, editor_header, preview_header, right_layout, left_panel, splitter = (
        view.size_layouts
    )
    for button in (
        view.upload_image_btn,
        view.upload_pdf_btn,
        view.handwriting_btn,
        view.copy_editor_btn,
        view.export_btn,
        view.workbench_btn,
    ):
        button.setMinimumWidth(button.sizeHint().width())
    left_layout.activate()
    editor_header.activate()
    preview_header.activate()
    right_layout.activate()
    right_margins = right_layout.contentsMargins()
    right_panel_width = (
        max(editor_header.minimumSize().width(), preview_header.minimumSize().width())
        + right_margins.left()
        + right_margins.right()
        + EDITOR_TOOLBAR_RIGHT_MARGIN
    )
    required_width = max(
        DEFAULT_MAIN_WINDOW_SIZE[0],
        left_panel.minimumSizeHint().width()
        + splitter.handleWidth()
        + right_panel_width,
    )
    view.setMinimumSize(required_width, DEFAULT_MAIN_WINDOW_SIZE[1])
    view.resize(required_width, DEFAULT_MAIN_WINDOW_SIZE[1])
