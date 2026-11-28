"""Edit recognized text and render its preview in the handwriting window."""

from __future__ import annotations

from PyQt6.QtCore import QSignalBlocker, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from editor.source_editor import SourceEditor
from localization.manager import translate as tr
from preview.math_preview import get_mathjax_base_url

from .latex_preview import (
    build_handwriting_preview_html,
    normalize_latex_preview_source,
)

try:
    from PyQt6.QtWebEngineCore import QWebEngineSettings
except Exception:
    QWebEngineSettings = None
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView as PreviewWebView
except Exception:
    PreviewWebView = None


class HandwritingResultPanel(QWidget):
    text_changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("handwritingRightPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 0, 0, 0)
        layout.setSpacing(12)
        result_section = QWidget(self)
        result_section.setObjectName("handwritingSubPanel")
        result_layout = QVBoxLayout(result_section)
        result_layout.setContentsMargins(14, 12, 14, 14)
        result_layout.setSpacing(10)
        result_header = QHBoxLayout()
        result_header.setContentsMargins(0, 0, 0, 0)
        result_header.setSpacing(8)
        result_title = QLabel(tr("LaTeX 结果"))
        result_title.setObjectName("handwritingSectionTitle")
        result_header.addWidget(result_title)
        result_header.addStretch(1)
        result_layout.addLayout(result_header)
        self._editor = SourceEditor(self)
        self._editor.setPlaceholderText(
            tr("手写识别结果会显示在这里，可直接手动修正。")
        )
        self._editor.setMinimumHeight(150)
        result_layout.addWidget(self._editor)
        layout.addWidget(result_section)
        preview_section = QWidget(self)
        preview_section.setObjectName("handwritingSubPanel")
        preview_layout = QVBoxLayout(preview_section)
        preview_layout.setContentsMargins(14, 12, 14, 14)
        preview_layout.setSpacing(10)
        preview_title = QLabel(tr("实时预览"))
        preview_title.setObjectName("handwritingSectionTitle")
        preview_layout.addWidget(preview_title)
        if PreviewWebView is not None:
            preview = PreviewWebView(self)
            preview.setObjectName("handwritingPreviewView")
            if QWebEngineSettings is not None:
                try:
                    settings = preview.settings()
                    if settings is not None:
                        settings.setAttribute(
                            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls,
                            True,
                        )
                        settings.setAttribute(
                            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,
                            True,
                        )
                except Exception:
                    pass
            preview.setMinimumHeight(280)
        else:
            preview = QLabel(tr("WebEngine 不可用，无法显示公式预览。"))
            preview.setWordWrap(True)
        self._preview = preview
        preview_layout.addWidget(preview, 1)
        layout.addWidget(preview_section, 1)
        self._editor.textChanged.connect(self.text_changed)

    def text(self) -> str:
        return self._editor.toPlainText().strip()

    def set_result(self, text: str, output_mode: str) -> None:
        content = text.replace("\r\n", "\n").strip()
        if output_mode == "latex":
            content = normalize_latex_preview_source(content)
        with QSignalBlocker(self._editor):
            self._editor.setPlainText(content)
        self.refresh_preview(output_mode)

    def refresh_preview(self, output_mode: str) -> None:
        text = self.text()
        if output_mode == "latex":
            text = normalize_latex_preview_source(text)
        if isinstance(self._preview, QLabel):
            self._preview.setText(
                tr("WebEngine 不可用。\n\n当前内容:\n") + (text or "<empty>")
            )
            return
        html = build_handwriting_preview_html(text, output_mode)
        base_url = get_mathjax_base_url()
        try:
            self._preview.setHtml(html, base_url)
        except Exception:
            pass
