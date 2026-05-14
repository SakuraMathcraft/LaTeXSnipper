"""Recognition result dialog builder."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QTextEdit, QVBoxLayout
from qfluentwidgets import BodyLabel, FluentIcon, PrimaryPushButton, PrimaryToolButton, PushButton

from preview.math_preview import build_math_html, dialog_theme_tokens, get_mathjax_base_url
from runtime.config_manager import normalize_content_type
from ui.window_helpers import apply_no_minimize_window_flags


def show_predict_result_dialog(
    *,
    parent,
    code: str,
    current_mode: str,
    result_screen_index: int | None,
    mode_title: Callable[[str], str],
    ensure_webengine_loaded: Callable[[], bool],
    build_mixed_html: Callable[[str], str],
    show_export_menu_for_source: Callable,
    accept_latex: Callable[[QDialog, QTextEdit], None],
    set_pin_button_style: Callable[[object, bool], None],
    set_pinned: Callable[[QDialog, object, bool], None],
    move_to_screen: Callable[[QDialog, int | None], None],
    clear_dialog_ref: Callable[[QDialog], None],
) -> QDialog:
    dlg = QDialog(parent)
    apply_no_minimize_window_flags(dlg)
    dlg.setWindowTitle("识别结果")
    dlg.resize(700, 500)
    dlg.setWindowModality(Qt.WindowModality.NonModal)
    dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    dlg._predict_result_mode = current_mode
    dlg._predict_result_pinned = False
    dlg.destroyed.connect(lambda *_args, _d=dlg: clear_dialog_ref(_d))

    lay = QVBoxLayout(dlg)

    info = BodyLabel(mode_title(current_mode))
    dlg._predict_result_info_label = info
    header_row = QHBoxLayout()
    header_row.addWidget(info)
    header_row.addStretch()
    pin_btn = PrimaryToolButton(FluentIcon.PIN, dlg)
    pin_btn.setCheckable(True)
    pin_btn.setFixedSize(30, 30)
    set_pin_button_style(pin_btn, False)
    header_row.addWidget(pin_btn)
    lay.addLayout(header_row)

    te = QTextEdit()
    te.setText(code)
    dlg._predict_result_editor = te
    lay.addWidget(te)

    if normalize_content_type(current_mode) == "mathcraft":
        preview_label = BodyLabel("公式预览：")
        lay.addWidget(preview_label)

        if ensure_webengine_loaded():
            from PyQt6.QtWebEngineWidgets import QWebEngineView

            preview_view = QWebEngineView()
            preview_view.setMinimumHeight(150)
            preview_view.setHtml(build_math_html(code), get_mathjax_base_url())
            lay.addWidget(preview_view, 1)

            render_timer = QTimer(dlg)
            render_timer.setSingleShot(True)

            def do_render():
                latex = te.toPlainText().strip()
                if latex and preview_view:
                    preview_view.setHtml(build_math_html(latex), get_mathjax_base_url())

            render_timer.timeout.connect(do_render)
            te.textChanged.connect(lambda: render_timer.start(300))
        else:
            fallback = QLabel("WebEngine 未加载，无法渲染预览")
            fallback.setStyleSheet(f"color: {dialog_theme_tokens()['muted']}; padding: 10px;")
            lay.addWidget(fallback)

    elif current_mode == "mathcraft_mixed":
        preview_label = BodyLabel("混合内容预览：")
        lay.addWidget(preview_label)

        if ensure_webengine_loaded():
            from PyQt6.QtWebEngineWidgets import QWebEngineView

            preview_view = QWebEngineView()
            preview_view.setMinimumHeight(150)
            preview_view.setHtml(build_mixed_html(code), get_mathjax_base_url())
            lay.addWidget(preview_view, 1)

            render_timer = QTimer(dlg)
            render_timer.setSingleShot(True)

            def do_render_mixed():
                content = te.toPlainText().strip()
                if content and preview_view:
                    preview_view.setHtml(build_mixed_html(content), get_mathjax_base_url())

            render_timer.timeout.connect(do_render_mixed)
            te.textChanged.connect(lambda: render_timer.start(300))

    elif current_mode == "mathcraft_text":
        preview_label = BodyLabel("文本预览：")
        lay.addWidget(preview_label)

        preview_text = QTextEdit()
        preview_text.setReadOnly(True)
        preview_text.setPlainText(code)
        preview_text.setMinimumHeight(100)
        lay.addWidget(preview_text, 1)

        def update_preview():
            preview_text.setPlainText(te.toPlainText())

        te.textChanged.connect(update_preview)

    btn_row = QHBoxLayout()
    btn_row.addStretch()
    export_btn = PushButton(FluentIcon.SHARE, "导出")
    export_btn.setFixedHeight(32)
    export_btn.clicked.connect(
        lambda: show_export_menu_for_source(
            export_btn,
            lambda: te.toPlainText(),
            empty_hint="识别结果为空",
            info_parent=dlg,
        )
    )
    confirm_btn = PrimaryPushButton(FluentIcon.ACCEPT, "确定")
    confirm_btn.setFixedHeight(32)
    confirm_btn.clicked.connect(lambda: accept_latex(dlg, te))
    btn_row.addWidget(export_btn)
    btn_row.addWidget(confirm_btn)
    lay.addLayout(btn_row)
    pin_btn.toggled.connect(lambda checked: set_pinned(dlg, pin_btn, checked))

    move_to_screen(dlg, result_screen_index)
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
    return dlg
