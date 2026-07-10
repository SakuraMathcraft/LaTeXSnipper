from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtWidgets import QDialog, QLabel, QScrollArea, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, FluentIcon, PrimaryPushButton

from preview.math_preview import dialog_theme_tokens, is_dark_ui


class ExternalModelHelpWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._theme_is_dark_cached = None
        self._title_label = None
        self._section_title_labels = []
        self._section_body_labels = []
        self.setWindowFlags(
            (
                self.windowFlags()
                | Qt.WindowType.CustomizeWindowHint
                | Qt.WindowType.WindowTitleHint
                | Qt.WindowType.WindowSystemMenuHint
                | Qt.WindowType.WindowCloseButtonHint
            )
            & ~Qt.WindowType.WindowMinimizeButtonHint
            & ~Qt.WindowType.WindowMaximizeButtonHint
            & ~Qt.WindowType.WindowMinMaxButtonsHint
            & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        self.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, False)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, True)
        self.setWindowTitle("外部模型配置说明")
        self.setFixedSize(500, 600)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self._title_label = QLabel("外部模型使用教程")
        layout.addWidget(self._title_label)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        content = QWidget(scroll)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)

        self._add_section(
            content_layout,
            "适用范围",
            "支持 Ollama、OpenAI-compatible 和 MinerU Local。线上接口需要确认鉴权、模型名、额度和服务协议。",
        )
        self._add_section(
            content_layout,
            "字段说明",
            "协议决定请求格式。Base URL 填服务根地址或服务商提供的 /v1 API 前缀，不要填写 /chat/completions、/api/chat 或 /file_parse 这类具体接口。模型名必须与服务中实际可用名称完全一致。API Key 本地加密保存。",
        )
        self._add_section(
            content_layout,
            "提示词边界",
            "提示词模板同时决定请求内容和结果类型。自定义提示词优先级最高，会覆盖普通图片、截图、手写以及 OpenAI-compatible / Ollama PDF 识别的内置模板。PDF 导出格式和 DPI 仍在 PDF 入口选择；MinerU Local 不使用提示词。",
        )
        self._add_section(
            content_layout,
            "本地 Ollama",
            "协议选择 Ollama，Base URL 填 http://127.0.0.1:11434，模型名填 qwen2.5vl:7b、glm-ocr 或实际 pull 的模型名，API Key 留空。",
        )
        self._add_section(
            content_layout,
            "MinerU Local",
            "协议选择 MinerU Local，Base URL 填本地服务根地址，例如 http://127.0.0.1:8000。解析接口路径和健康检查路径按实际服务填写，常见值为 /file_parse 和 /health。",
        )
        self._add_section(
            content_layout,
            "线上接口",
            "按服务要求选择 OpenAI-compatible 或 Ollama。Base URL 填服务商提供的 HTTPS 根地址或 /v1 API 前缀。模型名和 API Key 以服务商控制台为准。",
        )
        self._add_section(
            content_layout,
            "排查顺序",
            "先应用预设，再改成真实模型名，然后测试连接。连接通过后先测截图或图片识别，再测 PDF。PDF 效果不稳时优先调整 DPI。",
        )

        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        close_btn = PrimaryPushButton(FluentIcon.CLOSE, "关闭")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)
        self._apply_theme_styles(force=True)

    def _add_section(self, layout: QVBoxLayout, title: str, body: str) -> None:
        title_label = BodyLabel(title)
        self._section_title_labels.append(title_label)
        layout.addWidget(title_label)

        body_label = QLabel(body)
        body_label.setWordWrap(True)
        body_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._section_body_labels.append(body_label)
        layout.addWidget(body_label)

    def _apply_theme_styles(self, force: bool = False) -> None:
        dark = is_dark_ui()
        if not force and self._theme_is_dark_cached is dark:
            return
        self._theme_is_dark_cached = dark
        tokens = dialog_theme_tokens()
        if self._title_label is not None:
            self._title_label.setStyleSheet(
                f"font-size: 18px; font-weight: 600; color: {tokens['text']};"
            )
        for label in self._section_title_labels:
            label.setStyleSheet(f"font-weight: 600; color: {tokens['text']};")
        for label in self._section_body_labels:
            label.setStyleSheet(f"color: {tokens['muted']}; line-height: 1.35;")

    def event(self, event):
        result = super().event(event)
        if event.type() in (
            QEvent.Type.StyleChange,
            QEvent.Type.PaletteChange,
            QEvent.Type.ApplicationPaletteChange,
        ):
            self._apply_theme_styles()
        return result

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_theme_styles(force=True)
