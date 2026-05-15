from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QLabel, QPlainTextEdit, QVBoxLayout
from qfluentwidgets import FluentIcon, PrimaryPushButton


class ExternalModelHelpWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
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
        title = QLabel("外部模型使用教程")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(title)
        editor = QPlainTextEdit(self)
        editor.setReadOnly(True)
        editor.setPlainText(
            "适用范围\n"
            "1. 本地接口：推荐，适合 Ollama、本地 OpenAI-compatible 服务。\n"
            "2. 线上接口：支持 OpenAI-compatible / Ollama 在线接口，但需要你自己确认鉴权、模型名和额度。\n\n"
            "字段说明\n"
            "1. 协议：必填。决定请求格式。\n"
            "2. Base URL：必填。本地示例 http://127.0.0.1:11434 ，线上示例 https://example.com 。\n"
            "3. 模型名：必填。必须与服务中实际可用的模型名称完全一致。\n"
            "4. API Key：选填。本地服务通常留空，线上接口通常必填。\n"
            "5. 超时：选填。默认 60 秒，模型较大或网络较慢时可适当提高。\n"
            "6. 输出偏好：选填。影响图片、截图、手写识别优先返回 LaTeX、Markdown 还是纯文本。\n"
            "7. 提示词模板 / 自定义提示词：选填。优先使用自定义提示词，留空则使用模板。\n\n"
            "提示词生效边界（重要）\n"
            "1. 自定义提示词优先级最高：只要填写，就会覆盖模板选择。\n"
            "2. 普通图片、截图、手写识别：使用当前设置中的输出偏好和提示词规则。\n"
            "3. PDF 外部模型识别：导出格式和 DPI 在 PDF 入口单独选择；默认固定使用通用文档恢复模板。\n"
            "4. 如果填写了自定义提示词，OpenAI-compatible / Ollama 的 PDF 识别也会优先使用自定义提示词。\n"
            "5. MinerU 原生协议：走原生文档接口，不使用上述模板/自定义提示词文本；解析模式由服务端接口决定是否采用。\n\n"
            "本地 Ollama 示例\n"
            "1. 协议：Ollama\n"
            "2. Base URL：http://127.0.0.1:11434\n"
            "3. 模型名：qwen2.5vl:7b 或 glm-ocr\n"
            "4. API Key：留空\n\n"
            "MinerU 示例\n"
            "1. 协议：MinerU\n"
            "2. Base URL：http://127.0.0.1:8000\n"
            "3. 解析接口路径：按实际服务填写，例如 /file_parse\n"
            "4. 健康检查路径：按实际服务填写，例如 /health\n\n"
            "线上接口示例\n"
            "1. 协议：按服务要求选择 OpenAI-compatible 或 Ollama\n"
            "2. Base URL：填写服务商提供的 HTTPS 地址\n"
            "3. 模型名：填写服务商控制台或模型列表中的真实名称\n"
            "4. API Key：填写服务商发放的密钥\n\n"
            "常见问题\n"
            "1. 测试连接失败：先确认服务已启动、地址可访问、协议选对。\n"
            "2. 模型名填写错误：通常会返回 404、model not found、unknown model 或类似报错。\n"
            "3. 本地接口连不上：先用 curl 或浏览器访问 Base URL 对应接口确认服务是否真的在运行。\n"
            "4. 线上接口失败：优先检查 API Key、账户额度、IP 限制和模型权限。\n"
            "5. PDF 结果不稳定：可优先调整 DPI；清晰文档可尝试更低 DPI，普通文档建议 140-170 DPI。\n\n"
            "建议顺序\n"
            "1. 先应用预设。\n"
            "2. 再把模型名改成你实际部署或购买的模型名。\n"
            "3. 点测试连接。\n"
            "4. 先测截图 / 图片识别，再测 PDF。\n"
            "5. PDF 若效果不稳，优先调整 DPI，再考虑改模型或自定义提示词。"
        )
        layout.addWidget(editor, 1)
        close_btn = PrimaryPushButton(FluentIcon.CLOSE, "关闭")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)
