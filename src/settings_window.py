import os, sys, subprocess, shutil
from pathlib import Path
import time
import pyperclip
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QEvent, QThread
from PyQt6.QtWidgets import (QDialog, QLineEdit, QVBoxLayout, QLabel, QHBoxLayout, QWidget, QFileDialog, QInputDialog, QMessageBox, QCheckBox, QScrollArea, QPlainTextEdit)
from qfluentwidgets import FluentIcon, PushButton, PrimaryPushButton, ComboBox, InfoBar, InfoBarPosition, MessageBox
from updater import check_update_dialog
from deps_bootstrap import custom_warning_dialog
from backend.torch_runtime import (
    TORCH_CUDA_MATRIX,
    TORCH_CPU_PLAN,
    parse_cuda_ver_from_text,
    pick_torch_cuda_plan,
    detect_torch_gpu_plan,
    detect_torch_info,
    inject_shared_torch_env,
)
from backend.external_model import (
    ExternalModelConnectionWorker,
    PRESET_ITEMS,
    get_preset,
    load_config_from_mapping,
)
from core.restart_contract import build_restart_with_wizard_launch


def _subprocess_creationflags() -> int:
    if os.name != "nt":
        return 0
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))


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
            "2. 线上接口：兼容部分 OpenAI-compatible / Ollama 在线接口，但需要你自己确认鉴权、模型名和额度。\n\n"
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
            "3. 解析接口路径：按实际服务填写，例如 /v1/parse\n"
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


class SettingsWindow(QDialog):
    """设置窗口 - 使用 QDialog 作为基类"""
    model_changed = pyqtSignal(str)
    env_torch_probe_done = pyqtSignal(str, object, str)
    pix2text_pkg_probe_done = pyqtSignal(bool)
    latex_path_test_done = pyqtSignal(bool, str, str, str, str)
    latex_auto_detect_done = pyqtSignal(bool, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model_selection_syncing = False
        self._latex_test_in_progress = False
        self._latex_detect_in_progress = False
        self._external_test_thread = None
        self._external_test_worker = None
        self._external_help_window = None
        self._compute_mode_state = "unknown"
        self._theme_is_dark_cached = None
        self.setWindowFlags(
            (
                self.windowFlags()
                | Qt.WindowType.CustomizeWindowHint
                | Qt.WindowType.WindowTitleHint
                | Qt.WindowType.WindowSystemMenuHint
                | Qt.WindowType.WindowCloseButtonHint
                | Qt.WindowType.WindowMaximizeButtonHint
            )
            & ~Qt.WindowType.WindowMinimizeButtonHint
            & ~Qt.WindowType.WindowContextHelpButtonHint
            & ~Qt.WindowType.WindowMinMaxButtonsHint
        )
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
        self.setWindowTitle("设置")
        # 默认宽度加大，避免 InfoBar 文案被截断
        self.resize(600, 700)
        self.setMinimumWidth(600)
        self.setMinimumHeight(700)
        root = QVBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.content_widget = QWidget(self)
        lay = QVBoxLayout(self.content_widget)
        lay.setSpacing(8)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setWidget(self.content_widget)
        root.addWidget(self.scroll_area)
        self._pix2text_pkg_ready = False
        self._torch_probe_seq = {"pix2text": 0}
        # 缓存慢探测结果，避免频繁点击时阻塞 UI
        self._probe_cache_ttl_sec = 45.0
        self._cached_gpu_plan = None
        self._cached_gpu_note = ""
        self._cached_gpu_ts = 0.0
        self._cached_main_torch_info = None
        self._cached_main_torch_py = ""
        self._cached_main_torch_ts = 0.0
        self._theme_mode_values = ["light", "dark", "auto"]
        # 模型选择区域
        lay.addWidget(QLabel("选择识别模型:"))
        # 使用下拉框支持内置模型与外部模型入口
        from qfluentwidgets import ComboBox
        self.model_combo = ComboBox()
        self.model_combo.setFixedHeight(36)
        # 添加识别模型选项
        self._model_options = [
            ("pix2text", "pix2text - 公式识别"),
            ("external_model", "外部模型..."),
        ]
        for key, label in self._model_options:
            self.model_combo.addItem(label, userData=key)
        lay.addWidget(self.model_combo)
        # 模型说明
        self.lbl_model_desc = QLabel()
        self.lbl_model_desc.setStyleSheet("color: #666; font-size: 11px; padding: 4px;")
        self.lbl_model_desc.setWordWrap(True)
        lay.addWidget(self.lbl_model_desc)
        # pix2text 环境选择
        self.pix2text_env_widget = QWidget()
        pix2text_env_layout = QHBoxLayout(self.pix2text_env_widget)
        pix2text_env_layout.setContentsMargins(0, 0, 0, 0)
        pix2text_env_layout.setSpacing(6)
        pix2text_env_layout.addWidget(QLabel("pix2text 运行环境:"))
        self.pix2text_pyexe_input = QLineEdit()
        self.pix2text_pyexe_input.setPlaceholderText("使用主依赖环境 python.exe")
        self.pix2text_pyexe_input.setFixedHeight(30)
        self.pix2text_pyexe_input.setReadOnly(True)
        pix2text_env_layout.addWidget(self.pix2text_pyexe_input)
        lay.addWidget(self.pix2text_env_widget)
        self.pix2text_env_hint = QLabel("提示：pix2text 统一使用主依赖环境。")
        self.pix2text_env_hint.setStyleSheet("color: #666; font-size: 10px; padding: 2px;")
        self.pix2text_env_hint.setWordWrap(True)
        lay.addWidget(self.pix2text_env_hint)
        # pix2text 推理设备检测
        self.pix2text_torch_status = QLabel("pix2text 设备: 未检测")
        self.pix2text_torch_status.setStyleSheet("color: #666; font-size: 10px; padding: 2px;")
        self.pix2text_torch_status.setWordWrap(True)
        lay.addWidget(self.pix2text_torch_status)
        # 安装/下载统一收敛到依赖向导，设置页不再提供模型下载/安装入口。
        self.pix2text_torch_btn_row = None
        self.pix2text_torch_install_gpu = None
        self.pix2text_torch_reinstall = None
        self.pix2text_torch_refresh = None
        self.pix2text_dl_widget = None
        self.pix2text_download_btn = None
        self.pix2text_open_btn = None
        # pix2text 识别类型（仅在 pix2text 可用时显示）
        self.pix2text_mode_widget = QWidget()
        pix2text_mode_layout = QHBoxLayout(self.pix2text_mode_widget)
        pix2text_mode_layout.setContentsMargins(0, 0, 0, 0)
        pix2text_mode_layout.setSpacing(6)
        pix2text_mode_layout.addWidget(QLabel("pix2text 识别类型:"))
        self.pix2text_mode_combo = ComboBox()
        self.pix2text_mode_combo.setFixedHeight(30)
        self.pix2text_mode_combo.addItem("公式", userData="formula")
        self.pix2text_mode_combo.addItem("混合(文字+公式)", userData="mixed")
        self.pix2text_mode_combo.addItem("纯文字", userData="text")
        self.pix2text_mode_combo.addItem("整页/版面", userData="page")
        self.pix2text_mode_combo.addItem("表格", userData="table")
        self.pix2text_mode_combo.currentIndexChanged.connect(self._on_pix2text_mode_changed)
        pix2text_mode_layout.addWidget(self.pix2text_mode_combo)
        lay.addWidget(self.pix2text_mode_widget)
        self.external_model_widget = QWidget()
        external_layout = QVBoxLayout(self.external_model_widget)
        external_layout.setContentsMargins(0, 6, 0, 0)
        external_layout.setSpacing(6)
        self.external_intro = QLabel(
            "先填写协议、Base URL 和模型名，再点击“测试连接”。\n"
            "图片/截图/手写使用这里的输出偏好与提示词；PDF 导出格式在 PDF 入口单独选择。"
        )
        self.external_intro.setWordWrap(True)
        self.external_intro.setStyleSheet("color: #666; font-size: 11px; padding: 4px;")
        external_layout.addWidget(self.external_intro)
        preset_row = QHBoxLayout()
        preset_row.setContentsMargins(0, 0, 0, 0)
        preset_row.setSpacing(6)
        preset_row.addWidget(QLabel("推荐预设:"))
        self.external_preset_combo = ComboBox()
        self.external_preset_combo.setFixedHeight(30)
        self.external_preset_combo.addItem("不使用预设", userData="")
        for key, label in PRESET_ITEMS:
            self.external_preset_combo.addItem(label, userData=key)
        preset_row.addWidget(self.external_preset_combo, 1)
        self.external_apply_preset_btn = PushButton(FluentIcon.ROTATE, "应用预设")
        self.external_apply_preset_btn.setFixedHeight(30)
        preset_row.addWidget(self.external_apply_preset_btn)
        external_layout.addLayout(preset_row)
        protocol_row = QHBoxLayout()
        protocol_row.setContentsMargins(0, 0, 0, 0)
        protocol_row.setSpacing(6)
        protocol_row.addWidget(QLabel("协议:"))
        self.external_provider_combo = ComboBox()
        self.external_provider_combo.setFixedHeight(30)
        self.external_provider_combo.addItem("OpenAI-compatible", userData="openai_compatible")
        self.external_provider_combo.addItem("Ollama", userData="ollama")
        self.external_provider_combo.addItem("MinerU", userData="mineru")
        protocol_row.addWidget(self.external_provider_combo, 1)
        external_layout.addLayout(protocol_row)
        self.external_base_url_input = QLineEdit()
        self.external_base_url_input.setPlaceholderText("必填：Base URL，例如本地 http://127.0.0.1:11434 或线上 https://api.example.com")
        self.external_base_url_input.setFixedHeight(32)
        external_layout.addWidget(self.external_base_url_input)
        self.external_model_name_input = QLineEdit()
        self.external_model_name_input.setPlaceholderText("必填：模型名，例如 qwen2.5vl:7b；必须与服务中的真实名称一致")
        self.external_model_name_input.setFixedHeight(32)
        external_layout.addWidget(self.external_model_name_input)
        self.external_api_key_input = QLineEdit()
        self.external_api_key_input.setPlaceholderText("选填：API Key。本地通常留空，线上接口通常必填")
        self.external_api_key_input.setFixedHeight(32)
        external_layout.addWidget(self.external_api_key_input)
        self.external_mineru_endpoint_input = QLineEdit()
        self.external_mineru_endpoint_input.setPlaceholderText("MinerU 解析接口路径（例如 /v1/parse）")
        self.external_mineru_endpoint_input.setFixedHeight(32)
        external_layout.addWidget(self.external_mineru_endpoint_input)
        self.external_mineru_test_endpoint_input = QLineEdit()
        self.external_mineru_test_endpoint_input.setPlaceholderText("MinerU 健康检查路径（例如 /health）")
        self.external_mineru_test_endpoint_input.setFixedHeight(32)
        external_layout.addWidget(self.external_mineru_test_endpoint_input)
        mineru_mode_row = QHBoxLayout()
        mineru_mode_row.setContentsMargins(0, 0, 0, 0)
        mineru_mode_row.setSpacing(6)
        mineru_mode_row.addWidget(QLabel("MinerU 解析模式:"))
        self.external_mineru_mode_combo = ComboBox()
        self.external_mineru_mode_combo.setFixedHeight(30)
        self.external_mineru_mode_combo.addItem("自动", userData="auto")
        self.external_mineru_mode_combo.addItem("文档", userData="document")
        self.external_mineru_mode_combo.addItem("页面", userData="page")
        mineru_mode_row.addWidget(self.external_mineru_mode_combo, 1)
        self.external_mineru_mode_row = QWidget()
        self.external_mineru_mode_row.setLayout(mineru_mode_row)
        external_layout.addWidget(self.external_mineru_mode_row)
        output_row = QHBoxLayout()
        output_row.setContentsMargins(0, 0, 0, 0)
        output_row.setSpacing(6)
        output_row.addWidget(QLabel("输出偏好(图片/手写):"))
        self.external_output_combo = ComboBox()
        self.external_output_combo.setFixedHeight(30)
        self.external_output_combo.addItem("LaTeX 优先", userData="latex")
        self.external_output_combo.addItem("Markdown", userData="markdown")
        self.external_output_combo.addItem("纯文本", userData="text")
        output_row.addWidget(self.external_output_combo, 1)
        output_row.addWidget(QLabel("超时(秒):"))
        self.external_timeout_input = QLineEdit()
        self.external_timeout_input.setPlaceholderText("60")
        self.external_timeout_input.setFixedHeight(30)
        self.external_timeout_input.setMaximumWidth(90)
        output_row.addWidget(self.external_timeout_input)
        external_layout.addLayout(output_row)
        prompt_row = QHBoxLayout()
        prompt_row.setContentsMargins(0, 0, 0, 0)
        prompt_row.setSpacing(6)
        prompt_row.addWidget(QLabel("提示词模板(图片/手写):"))
        self.external_prompt_combo = ComboBox()
        self.external_prompt_combo.setFixedHeight(30)
        self.external_prompt_combo.addItem("公式 OCR", userData="ocr_formula_v1")
        self.external_prompt_combo.addItem("Markdown OCR", userData="ocr_markdown_v1")
        self.external_prompt_combo.addItem("纯文本 OCR", userData="ocr_text_v1")
        prompt_row.addWidget(self.external_prompt_combo, 1)
        external_layout.addLayout(prompt_row)
        self.external_custom_prompt_input = QLineEdit()
        self.external_custom_prompt_input.setPlaceholderText("自定义提示词（最高优先级；会覆盖图片/截图/手写模板。PDF 默认走通用文档模板；仅对 OpenAI-compatible/Ollama 生效）")
        self.external_custom_prompt_input.setFixedHeight(32)
        external_layout.addWidget(self.external_custom_prompt_input)
        self.external_status = QLabel("状态：未配置")
        self.external_status.setWordWrap(True)
        self.external_status.setStyleSheet("color: #666; font-size: 10px; padding: 2px;")
        external_layout.addWidget(self.external_status)
        self.external_hint = QLabel("建议先应用一个推荐预设，再把模型名替换成你本地部署或线上服务里实际可用的名称。")
        self.external_hint.setWordWrap(True)
        self.external_hint.setStyleSheet("color: #666; font-size: 10px; padding: 2px;")
        external_layout.addWidget(self.external_hint)
        external_btn_row = QHBoxLayout()
        external_btn_row.setContentsMargins(0, 0, 0, 0)
        external_btn_row.setSpacing(6)
        self.external_test_btn = PrimaryPushButton(FluentIcon.SPEED_HIGH, "测试连接")
        self.external_test_btn.setFixedHeight(32)
        external_btn_row.addWidget(self.external_test_btn)
        self.external_help_btn = PushButton(FluentIcon.INFO, "查看说明")
        self.external_help_btn.setFixedHeight(32)
        external_btn_row.addWidget(self.external_help_btn)
        external_layout.addLayout(external_btn_row)
        lay.addWidget(self.external_model_widget)
        # 已移除 UniMERNet UI，当前由 pix2text 与 external_model 两条链路并存。
        self.unimernet_widget = None
        self.unimernet_env_widget = None
        self.unimernet_env_hint = None
        self.unimernet_torch_status = None
        self.unimernet_torch_btn_row = None
        self.lbl_compute_mode = QLabel()
        self.lbl_compute_mode.setStyleSheet("color: #666; font-size: 11px; padding: 4px;")
        lay.addWidget(self.lbl_compute_mode)
        self._update_compute_mode_label()
        # 分隔
        lay.addSpacing(12)
        # ============ 外观主题设置 ============
        lay.addWidget(QLabel("外观主题:"))
        self.theme_mode_combo = ComboBox()
        self.theme_mode_combo.setFixedHeight(36)
        self.theme_mode_combo.addItem("浅色", userData="light")
        self.theme_mode_combo.addItem("深色", userData="dark")
        self.theme_mode_combo.addItem("跟随系统", userData="auto")
        lay.addWidget(self.theme_mode_combo)
        # ============ 渲染引擎设置 ============
        lay.addWidget(QLabel("公式渲染引擎:"))
        # 渲染引擎选择 - 使用 qfluentwidgets ComboBox 保持一致的外观
        from qfluentwidgets import ComboBox as FluentComboBox
        self.render_engine_combo = FluentComboBox()
        self.render_engine_combo.setFixedHeight(36)
        # 添加项目
        self.render_engine_combo.addItems([
            "自动检测 (MathJax CDN 备选)",
            "本地 MathJax",
            "CDN MathJax",
            "LaTeX + pdflatex",
            "LaTeX + xelatex",
        ])
        # 保存对应的数据
        self._render_modes = ["auto", "mathjax_local", "mathjax_cdn", "latex_pdflatex", "latex_xelatex"]
        lay.addWidget(self.render_engine_combo)
        # LaTeX 选项容器（仅在选择 LaTeX 时显示）
        self.latex_options_widget = QWidget()
        latex_layout = QVBoxLayout(self.latex_options_widget)
        latex_layout.setContentsMargins(0, 8, 0, 0)
        latex_layout.setSpacing(6)
        # LaTeX 路径选择
        latex_path_layout = QHBoxLayout()
        latex_path_layout.addWidget(QLabel("LaTeX 路径:"))
        self.latex_path_input = QLineEdit()
        self.latex_path_input.setPlaceholderText("例：C:\\Program Files\\MiKTeX\\miktex\\bin\\x64\\pdflatex.exe")
        self.latex_path_input.setFixedHeight(32)
        latex_path_layout.addWidget(self.latex_path_input)
        self.btn_browse_latex = PushButton(FluentIcon.FOLDER, "浏览")
        self.btn_browse_latex.setFixedWidth(80)
        self.btn_browse_latex.setFixedHeight(32)
        latex_path_layout.addWidget(self.btn_browse_latex)
        latex_layout.addLayout(latex_path_layout)
        # LaTeX 操作按钮
        latex_btn_layout = QHBoxLayout()
        self.btn_detect_latex = PushButton(FluentIcon.SEARCH, "自动检测")
        self.btn_detect_latex.setFixedHeight(32)
        latex_btn_layout.addWidget(self.btn_detect_latex)
        self.btn_test_latex = PrimaryPushButton("验证路径")
        self.btn_test_latex.setFixedHeight(32)
        latex_btn_layout.addWidget(self.btn_test_latex)
        latex_layout.addLayout(latex_btn_layout)
        # LaTeX 说明
        self.lbl_latex_desc = QLabel("💡 需要本地安装 MiKTeX 或 TeX Live，验证通过后才能使用")
        self.lbl_latex_desc.setStyleSheet("color: #666; font-size: 10px; padding: 4px;")
        self.lbl_latex_desc.setWordWrap(True)
        latex_layout.addWidget(self.lbl_latex_desc)
        self.latex_options_widget.setVisible(False)  # 默认隐藏
        lay.addWidget(self.latex_options_widget)
        # 分隔
        lay.addSpacing(8)
        # 检查更新
        lay.addWidget(QLabel("检查更新:"))
        self.btn_update = PushButton(FluentIcon.UPDATE, "检查更新")
        self.btn_update.setFixedHeight(36)
        lay.addWidget(self.btn_update)
        # 启动行为
        lay.addWidget(QLabel("启动行为:"))
        self.startup_console_checkbox = QCheckBox("启动时显示日志窗口（调试）")
        startup_console_pref = False
        try:
            if self.parent() and hasattr(self.parent(), "cfg"):
                startup_console_pref = self.parent().cfg.get("show_startup_console", False)
        except Exception:
            startup_console_pref = False
        self.startup_console_checkbox.setChecked(self._to_bool(startup_console_pref))
        self.startup_console_checkbox.setToolTip("默认关闭。开启后将显示初始化与运行日志窗口")
        lay.addWidget(self.startup_console_checkbox)
        # 分隔
        lay.addSpacing(8)
        # 高级功能：打开终端（慎用）
        lay.addWidget(QLabel("高级 (慎用):"))
        terminal_row = QWidget()
        terminal_layout = QHBoxLayout(terminal_row)
        terminal_layout.setContentsMargins(0, 0, 0, 0)
        terminal_layout.setSpacing(6)
        self.terminal_env_combo = ComboBox()
        self.terminal_env_combo.setFixedHeight(36)
        self.terminal_env_combo.addItem("主环境（程序 / pix2text）", userData="main")
        terminal_layout.addWidget(self.terminal_env_combo)
        self.btn_terminal = PushButton(FluentIcon.COMMAND_PROMPT, "打开环境终端")
        self.btn_terminal.setFixedHeight(36)
        self.btn_terminal.setToolTip("打开所选环境的终端，可手动安装/修复依赖。\n⚠️ 请谨慎操作，错误的命令可能损坏环境！")
        terminal_layout.addWidget(self.btn_terminal)
        lay.addWidget(terminal_row)
        # 依赖管理向导 + 缓存目录
        deps_row = QWidget()
        deps_row_layout = QHBoxLayout(deps_row)
        deps_row_layout.setContentsMargins(0, 0, 0, 0)
        deps_row_layout.setSpacing(6)
        self.btn_deps_wizard = PushButton(FluentIcon.DEVELOPER_TOOLS, "依赖管理向导")
        self.btn_deps_wizard.setFixedHeight(36)
        self.btn_deps_wizard.setToolTip("打开依赖管理向导，可安装/升级 GPU 加速层、模型依赖等")
        deps_row_layout.addWidget(self.btn_deps_wizard, 1)
        self.btn_open_pix2text_cache = PushButton(FluentIcon.FOLDER, "打开缓存目录")
        self.btn_open_pix2text_cache.setFixedHeight(36)
        self.btn_open_pix2text_cache.setToolTip("打开 pix2text 模型缓存目录（默认位于 APPDATA/pix2text）")
        deps_row_layout.addWidget(self.btn_open_pix2text_cache, 1)
        lay.addWidget(deps_row)
        # 弹性空间
        lay.addStretch()
        # 连接信号
        self.model_combo.currentIndexChanged.connect(self._on_model_combo_changed)
        self.env_torch_probe_done.connect(self._set_env_torch_ui)
        self.pix2text_pkg_probe_done.connect(self._set_pix2text_pkg_ready)
        self.btn_update.clicked.connect(lambda: check_update_dialog(self))
        self.btn_terminal.clicked.connect(lambda: self._open_terminal())
        self.terminal_env_combo.currentIndexChanged.connect(self._on_terminal_env_changed)
        self.btn_deps_wizard.clicked.connect(self._open_deps_wizard)
        self.btn_open_pix2text_cache.clicked.connect(self._open_pix2text_cache_dir)
        self.startup_console_checkbox.stateChanged.connect(self._on_startup_console_changed)
        self.theme_mode_combo.currentIndexChanged.connect(self._on_theme_mode_changed)
        # 渲染引擎相关信号
        self.render_engine_combo.currentIndexChanged.connect(self._on_render_engine_changed)
        self.latex_path_test_done.connect(self._on_latex_path_test_done)
        self.latex_auto_detect_done.connect(self._on_latex_auto_detect_done)
        self.btn_browse_latex.clicked.connect(self._browse_latex_path)
        self.btn_detect_latex.clicked.connect(self._detect_latex)
        self.btn_test_latex.clicked.connect(self._test_latex_path)
        self.latex_path_input.textChanged.connect(self._on_latex_path_changed)
        self.external_apply_preset_btn.clicked.connect(self._apply_external_preset)
        self.external_test_btn.clicked.connect(self._test_external_model_connection)
        self.external_help_btn.clicked.connect(self._show_external_model_help)
        self.external_preset_combo.currentIndexChanged.connect(self._on_external_preset_changed)
        self.external_provider_combo.currentIndexChanged.connect(self._on_external_config_changed)
        self.external_provider_combo.currentIndexChanged.connect(self._on_external_provider_changed)
        self.external_output_combo.currentIndexChanged.connect(self._on_external_config_changed)
        self.external_mineru_mode_combo.currentIndexChanged.connect(self._on_external_config_changed)
        self.external_prompt_combo.currentIndexChanged.connect(self._on_external_config_changed)
        self.external_base_url_input.textChanged.connect(self._on_external_config_changed)
        self.external_model_name_input.textChanged.connect(self._on_external_config_changed)
        self.external_api_key_input.textChanged.connect(self._on_external_config_changed)
        self.external_mineru_endpoint_input.textChanged.connect(self._on_external_config_changed)
        self.external_mineru_test_endpoint_input.textChanged.connect(self._on_external_config_changed)
        self.external_timeout_input.textChanged.connect(self._on_external_config_changed)
        self.external_custom_prompt_input.textChanged.connect(self._on_external_config_changed)
        # 初始化选择状态
        self._init_model_combo()
        self._update_model_desc()
        self._init_theme_mode_combo()
        self._init_render_engine()
        self._load_latex_settings()
        # 后台预热探测缓存，减少首次点击“终端/安装GPU”卡顿
        QTimer.singleShot(120, self._warm_probe_cache_async)
        self.apply_theme_styles(force=True)

    def _is_dark_mode(self) -> bool:
        try:
            from qfluentwidgets import isDarkTheme
            return bool(isDarkTheme())
        except Exception:
            pal = self.palette().window().color()
            return ((pal.red() + pal.green() + pal.blue()) / 3.0) < 128

    def _normalize_theme_mode(self, value: str | None) -> str:
        mode = str(value or "auto").strip().lower()
        return mode if mode in self._theme_mode_values else "auto"

    def _init_theme_mode_combo(self):
        mode = "auto"
        try:
            if self.parent() and hasattr(self.parent(), "cfg"):
                mode = self._normalize_theme_mode(self.parent().cfg.get("theme_mode", "auto"))
                self.parent().cfg.set("theme_mode", mode)
        except Exception:
            mode = "auto"
        try:
            idx = self._theme_mode_values.index(mode)
        except Exception:
            idx = 2
        prev = self.theme_mode_combo.blockSignals(True)
        self.theme_mode_combo.setCurrentIndex(idx)
        self.theme_mode_combo.blockSignals(prev)

    def _on_theme_mode_changed(self, index: int):
        mode = "auto"
        if index >= 0:
            value = self.theme_mode_combo.itemData(index)
            mode = self._normalize_theme_mode(value)
        try:
            if self.parent() and hasattr(self.parent(), "cfg"):
                self.parent().cfg.set("theme_mode", mode)
        except Exception:
            pass
        try:
            if self.parent() and hasattr(self.parent(), "apply_app_theme_mode"):
                self.parent().apply_app_theme_mode(mode, refresh_preview=True)
        except Exception:
            pass
        mapping = {"light": "浅色", "dark": "深色", "auto": "跟随系统"}
        self._show_info("主题已应用", f"当前主题: {mapping.get(mode, mode)}", "success")

    def _theme_tokens(self) -> dict:
        if self._is_dark_mode():
            return {
                "muted": "#b6beca",
                "compute_gpu": "#7bd88f",
                "compute_cpu": "#ffb35c",
                "compute_unknown": "#9ea7b3",
            }
        return {
            "muted": "#666666",
            "compute_gpu": "#2e7d32",
            "compute_cpu": "#f57c00",
            "compute_unknown": "#666666",
        }

    def _compute_label_color(self) -> str:
        t = self._theme_tokens()
        if self._compute_mode_state == "gpu":
            return t["compute_gpu"]
        if self._compute_mode_state == "cpu":
            return t["compute_cpu"]
        return t["compute_unknown"]

    def apply_theme_styles(self, force: bool = False):
        dark = self._is_dark_mode()
        if not force and self._theme_is_dark_cached is dark:
            return
        self._theme_is_dark_cached = dark
        t = self._theme_tokens()
        if hasattr(self, "lbl_model_desc") and self.lbl_model_desc is not None:
            self.lbl_model_desc.setStyleSheet(f"color: {t['muted']}; font-size: 11px; padding: 4px;")
        if hasattr(self, "pix2text_env_hint") and self.pix2text_env_hint is not None:
            self.pix2text_env_hint.setStyleSheet(f"color: {t['muted']}; font-size: 10px; padding: 2px;")
        if hasattr(self, "pix2text_torch_status") and self.pix2text_torch_status is not None:
            self.pix2text_torch_status.setStyleSheet(f"color: {t['muted']}; font-size: 10px; padding: 2px;")
        if hasattr(self, "lbl_latex_desc") and self.lbl_latex_desc is not None:
            self.lbl_latex_desc.setStyleSheet(f"color: {t['muted']}; font-size: 10px; padding: 4px;")
        if hasattr(self, "lbl_compute_mode") and self.lbl_compute_mode is not None:
            self.lbl_compute_mode.setStyleSheet(
                f"color: {self._compute_label_color()}; font-size: 11px; padding: 4px;"
            )

    def event(self, e):
        result = super().event(e)
        try:
            if e.type() in (
                QEvent.Type.StyleChange,
                QEvent.Type.PaletteChange,
                QEvent.Type.ApplicationPaletteChange,
            ):
                self.apply_theme_styles()
        except Exception:
            pass
        return result

    def _warm_probe_cache_async(self):
        def worker():
            try:
                self._detect_torch_gpu_plan(allow_block=True)
            except Exception:
                pass
            try:
                self._get_main_torch_info_cached(allow_block=True)
            except Exception:
                pass
        import threading
        threading.Thread(target=worker, daemon=True).start()
    def _compiler_for_engine(self, engine: str) -> str:
        return "xelatex" if str(engine or "").strip() == "latex_xelatex" else "pdflatex"

    def _sync_latex_path_for_engine(self, engine: str) -> None:
        if not str(engine or "").startswith("latex_"):
            return
        target = self._compiler_for_engine(engine)
        target_exe = f"{target}.exe"
        other_exe = "pdflatex.exe" if target == "xelatex" else "xelatex.exe"
        current_path = (self.latex_path_input.text() or "").strip()
        if current_path:
            base = os.path.basename(current_path).lower()
            if base == other_exe:
                self.latex_path_input.setText(os.path.join(os.path.dirname(current_path), target_exe))
            return
        candidate = shutil.which(target) or target_exe
        if candidate:
            self.latex_path_input.setText(candidate)
    def _on_terminal_env_changed(self, index: int):
        mapping = {0: "main"}
        self._terminal_env_key = mapping.get(index, "main")

    def _to_bool(self, value) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return False

    def _on_startup_console_changed(self, state: int):
        # PyQt6 的 CheckState 不是可直接 int() 的枚举，直接读控件状态最稳妥。
        enabled = bool(self.startup_console_checkbox.isChecked())
        try:
            if self.parent() and hasattr(self.parent(), "cfg"):
                self.parent().cfg.set("show_startup_console", enabled)
        except Exception:
            pass
        try:
            if self.parent() and hasattr(self.parent(), "apply_startup_console_preference"):
                self.parent().apply_startup_console_preference(enabled)
        except Exception:
            pass
        self._show_info("设置已保存", "日志窗口显示偏好已更新（建议重启程序后完全生效）", "success")
    def _get_terminal_env_key(self) -> str:
        return "main"
    def _probe_module_installed(self, pyexe: str, module: str) -> bool:
        import subprocess
        if not pyexe or not os.path.exists(pyexe):
            return False
        code = f"import importlib.util, sys; sys.exit(0 if importlib.util.find_spec(\"{module}\") else 1)"
        try:
            try:
                res = subprocess.run(
                    [pyexe, "-c", code],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    creationflags=_subprocess_creationflags(),
                )
            except subprocess.TimeoutExpired:
                return False
            return res.returncode == 0
        except Exception:
            return False
    def _schedule_pix2text_pkg_probe(self):
        pyexe = self.pix2text_pyexe_input.text().strip()
        if not pyexe or not os.path.exists(pyexe):
            self._pix2text_pkg_ready = False
            self._update_pix2text_visibility()
            return
        def worker():
            ok = self._probe_module_installed(pyexe, "pix2text")
            try:
                self.pix2text_pkg_probe_done.emit(bool(ok))
            except Exception:
                pass
        import threading
        threading.Thread(target=worker, daemon=True).start()
    def _set_pix2text_pkg_ready(self, ready: bool):
        self._pix2text_pkg_ready = bool(ready)
        self._update_pix2text_visibility()
    def _infer_torch_info_from_env(self, pyexe: str) -> dict:
        try:
            from pathlib import Path
            p = Path(pyexe)
            env_root = p.parent.parent if p.name.lower() == "python.exe" else p.parent
            site = env_root / "Lib" / "site-packages"
            if not site.exists():
                return {}
            dist_infos = [d.name.lower() for d in site.glob("torch-*.dist-info")]
            if dist_infos:
                cuda_ver = ""
                for name in dist_infos:
                    if "+cu" in name:
                        cuda_ver = name.split("+cu", 1)[1].split("-", 1)[0]
                        break
                return {
                    "present": True,
                    "cuda_version": f"cu{cuda_ver}" if cuda_ver else "",
                    "cuda_available": True if cuda_ver else False,
                }
            if (site / "torch").exists():
                return {"present": True, "cuda_version": "", "cuda_available": False}
        except Exception:
            return {}
        return {}

    def _probe_torch_info(self, pyexe: str, env_key: str = "") -> dict:
        if not pyexe or not os.path.exists(pyexe):
            return {"present": False, "error": "python.exe not found"}
        run_env = os.environ.copy()
        try:
            key = "PIX2TEXT_SHARED_TORCH_SITE"
            shared_site = os.environ.get(key, "")
            run_env = inject_shared_torch_env(run_env, shared_site)
        except Exception:
            pass
        try:
            info = detect_torch_info(pyexe, timeout_sec=5, run_env=run_env)
            if info.get("present"):
                return info
            fallback = self._infer_torch_info_from_env(pyexe)
            if fallback:
                return fallback
            return info
        except Exception as e:
            return {"present": False, "error": str(e)}
        return {"present": False, "error": "probe failed"}
    def _set_env_torch_ui(self, env_key: str, info: dict, pyexe: str):
        env_key = "pix2text"
        label = self.pix2text_torch_status
        if info.get("error") == "timeout":
            label.setText(f"{env_key} 设备: 获取超时")
            return
        if not pyexe or not os.path.exists(pyexe):
            label.setText(f"{env_key} 设备: 环境未配置")
            return
        if not info.get("present"):
            label.setText(f"{env_key} 设备: 未安装 PyTorch（默认将为 CPU 版）")
            return
        cuda_ver = info.get("cuda_version")
        cuda_ok = info.get("cuda_available")
        if cuda_ver:
            suffix = "（CUDA 不可用）" if cuda_ok is False else ""
            label.setText(f"{env_key} 设备: GPU 版已安装{suffix}")
        else:
            label.setText(f"{env_key} 设备: CPU 版已安装")

    def _schedule_env_torch_probe(self, env_key: str):
        if env_key != "pix2text":
            return
        pyexe = self.pix2text_pyexe_input.text().strip()
        label = self.pix2text_torch_status
        label.setText(f"{env_key} 设备: 检测中...")
        def worker():
            info = self._probe_torch_info(pyexe, env_key=env_key)
            try:
                self.env_torch_probe_done.emit(env_key, info, pyexe)
            except Exception:
                pass
        import threading
        threading.Thread(target=worker, daemon=True).start()

    def _refresh_env_status(self, env_key: str):
        if env_key != "pix2text":
            return
        self._schedule_env_torch_probe(env_key)
        self._schedule_pix2text_pkg_probe()
    def _torch_cuda_matrix(self) -> list[dict]:
        # 统一复用 backend.torch_runtime 里的单一版本矩阵，避免多处硬编码漂移。
        return [dict(p) for p in TORCH_CUDA_MATRIX]

    def _torch_cpu_plan(self) -> dict:
        return dict(TORCH_CPU_PLAN)

    def _onnxruntime_gpu_spec_for_tag(self, tag: str | None) -> str:
        if (tag or "").lower() == "cu118":
            return "onnxruntime-gpu~=1.18.1"
        return "onnxruntime-gpu~=1.19.2"

    def _onnxruntime_cpu_spec(self) -> str:
        return "onnxruntime~=1.19.2"

    def _parse_cuda_ver_from_text(self, text: str) -> tuple[int, int] | None:
        return parse_cuda_ver_from_text(text)

    def _pick_torch_cuda_plan(self, major: int, minor: int) -> dict | None:
        plan, note = pick_torch_cuda_plan(major, minor)
        self._cuda_detect_note = note
        return dict(plan) if plan else None

    def _detect_torch_gpu_plan(self, allow_block: bool = True) -> dict | None:
        now = time.monotonic()
        ttl = float(getattr(self, "_probe_cache_ttl_sec", 45.0) or 45.0)
        cached_plan = getattr(self, "_cached_gpu_plan", None)
        cached_note = getattr(self, "_cached_gpu_note", "")
        cached_ts = float(getattr(self, "_cached_gpu_ts", 0.0) or 0.0)
        if (now - cached_ts) <= ttl and (cached_plan is not None or cached_note):
            self._cuda_detect_note = cached_note
            return dict(cached_plan) if isinstance(cached_plan, dict) else None
        if not allow_block:
            self._cuda_detect_note = cached_note
            return dict(cached_plan) if isinstance(cached_plan, dict) else None
        plan, note = detect_torch_gpu_plan(timeout_sec=5)
        self._cached_gpu_plan = dict(plan) if plan else None
        self._cached_gpu_note = note or ""
        self._cached_gpu_ts = now
        self._cuda_detect_note = note
        return dict(plan) if plan else None

    def _get_main_torch_info_cached(self, allow_block: bool = True) -> tuple[dict, str]:
        now = time.monotonic()
        ttl = float(getattr(self, "_probe_cache_ttl_sec", 45.0) or 45.0)
        cached_info = getattr(self, "_cached_main_torch_info", None)
        cached_py = getattr(self, "_cached_main_torch_py", "")
        cached_ts = float(getattr(self, "_cached_main_torch_ts", 0.0) or 0.0)
        if (now - cached_ts) <= ttl and isinstance(cached_info, dict) and cached_py:
            return dict(cached_info), str(cached_py)
        if not allow_block:
            return (dict(cached_info) if isinstance(cached_info, dict) else {}), str(cached_py or "")
        try:
            from backend.torch_runtime import infer_main_python, detect_torch_info
            main_py = infer_main_python()
            main_info = detect_torch_info(main_py, timeout_sec=6)
        except Exception:
            return {}, ""
        self._cached_main_torch_info = dict(main_info) if isinstance(main_info, dict) else {}
        self._cached_main_torch_py = str(main_py or "")
        self._cached_main_torch_ts = now
        return dict(self._cached_main_torch_info), self._cached_main_torch_py

    def _detect_cuda_tag(self) -> str | None:
        plan = self._detect_torch_gpu_plan()
        return plan["tag"] if plan else None

    def _resolve_shared_torch_site_for_mode(self, mode: str, allow_block: bool = True) -> str:
        """获取可复用的主环境 torch site-packages 路径。"""
        if allow_block:
            try:
                p = self.parent()
                if p and hasattr(p, "_resolve_shared_torch_site_for_mode"):
                    s = p._resolve_shared_torch_site_for_mode(mode)
                    if s and os.path.isdir(s):
                        return s
            except Exception:
                pass
        try:
            from backend.torch_runtime import mode_satisfies, python_site_packages
            main_info, main_py = self._get_main_torch_info_cached(allow_block=allow_block)
            if not main_info.get("present"):
                return ""
            if not mode_satisfies(main_info, mode):
                return ""
            site = python_site_packages(main_py)
            if site and (site / "torch").exists():
                return str(site)
        except Exception:
            pass
        return ""

    def _pix2text_install_steps(
        self,
        pyexe: str,
        mode: str,
        shared_site_hint: str = "",
        gpu_tag: str = "",
    ) -> list[str]:
        """
        可控分步安装，避免 pip 长时间回溯。
        仅共享 torch；不固定 numpy，不额外约束其它包。
        """
        common_flags = "--default-timeout 180 --retries 15 --prefer-binary --extra-index-url https://pypi.org/simple"
        shared_lit = (shared_site_hint or "").replace("\\", "\\\\").replace("'", "\\'")
        verify_code = (
            "import os,sys; "
            f"s=(os.environ.get('PIX2TEXT_SHARED_TORCH_SITE','') or os.environ.get('LATEXSNIPPER_SHARED_TORCH_SITE','') or r'{shared_lit}').strip(); "
            "added=(bool(s) and os.path.isdir(s) and s not in sys.path); "
            "(sys.path.insert(0,s) if added else None); "
            "tl=(os.path.join(s,'torch','lib') if s else ''); "
            "(os.add_dll_directory(tl) if (tl and os.path.isdir(tl) and hasattr(os,'add_dll_directory')) else None); "
            "os.environ['PATH']=((tl+os.pathsep+os.environ.get('PATH','')) if (tl and os.path.isdir(tl)) else os.environ.get('PATH','')); "
            "import torch; "
            "import torchvision; "
            "import importlib.util as _iu; (__import__('torchaudio') if _iu.find_spec('torchaudio') else None); "
            "(sys.path.remove(s) if (added and s in sys.path) else None); "
            "from pix2text import Pix2Text; "
            "print('pix2text ok')"
        )
        steps = [
            f"\"{pyexe}\" -m pip install -U pip setuptools wheel {common_flags}",
            f"\"{pyexe}\" -m pip uninstall -y optimum optimum-onnx optimum-intel",
            f"\"{pyexe}\" -m pip install -U \"transformers==4.55.4\" \"tokenizers==0.21.4\" {common_flags}",
            f"\"{pyexe}\" -m pip install -U \"optimum-onnx>=0.0.3\" {common_flags}",
            f"\"{pyexe}\" -m pip install -U \"pix2text==1.1.6\" {common_flags}",
            f"\"{pyexe}\" -m pip install -U \"pymupdf~=1.23.0\" {common_flags}",
        ]
        # pix2text 依赖链可能回拉 onnxruntime，末尾强制修正 CPU/GPU 最终状态（互斥）。
        if (mode or "").strip().lower() == "gpu":
            onnx_spec = self._onnxruntime_gpu_spec_for_tag(gpu_tag)
        else:
            onnx_spec = self._onnxruntime_cpu_spec()
        steps += [
            f"\"{pyexe}\" -m pip uninstall -y onnxruntime onnxruntime-gpu",
            f"\"{pyexe}\" -m pip install -U \"{onnx_spec}\" {common_flags}",
        ]
        steps.append(f"\"{pyexe}\" -c \"{verify_code}\"")
        return steps

    def _shared_torch_verify_cmd(self, pyexe: str, env_key: str, mode: str) -> str:
        """构造可复用主环境 torch 的校验命令（含 DLL/路径注入）。"""
        shared_site_hint = ""
        if env_key == "pix2text":
            try:
                shared_site_hint = self._resolve_shared_torch_site_for_mode(mode)
            except Exception:
                shared_site_hint = ""
        shared_lit = (shared_site_hint or "").replace("\\", "\\\\").replace("'", "\\'")
        verify_code = (
            "import os,sys; import os as _o; import importlib.util as _iu; "
            f"s=(os.environ.get('PIX2TEXT_SHARED_TORCH_SITE','') or os.environ.get('LATEXSNIPPER_SHARED_TORCH_SITE','') or r'{shared_lit}').strip(); "
            "added=(bool(s) and _o.path.isdir(s) and s not in sys.path); "
            "(sys.path.insert(0,s) if added else None); "
            "tl=(_o.path.join(s,'torch','lib') if s else ''); "
            "(_o.add_dll_directory(tl) if (tl and _o.path.isdir(tl) and hasattr(_o,'add_dll_directory')) else None); "
            "_o.environ['PATH']=((tl+_o.pathsep+_o.environ.get('PATH','')) if (tl and _o.path.isdir(tl)) else _o.environ.get('PATH','')); "
            "import torch; import torchvision; (__import__('torchaudio') if _iu.find_spec('torchaudio') else None); "
            "print('torch', getattr(torch,'__version__','')); "
            "print('cuda', bool(torch.cuda.is_available()), getattr(getattr(torch,'version',None),'cuda','')); "
            "(sys.path.remove(s) if (added and s in sys.path) else None)"
        )
        return f"\"{pyexe}\" -c \"{verify_code}\""

    def _install_env_torch(self, env_key: str, mode: str, include_model: bool = True):
        env_key = "pix2text"
        pyexe = self.pix2text_pyexe_input.text().strip()
        if not pyexe or not os.path.exists(pyexe):
            self._show_info("环境未配置", "请先完成依赖向导初始化主依赖环境。", "warning")
            return
        mode = (mode or "auto").strip().lower()
        if mode not in ("cpu", "gpu"):
            mode = "cpu"
        # Persist per-env torch preference for runtime shared-layer routing.
        try:
            if self.parent() and hasattr(self.parent(), "cfg"):
                self.parent().cfg.set(f"{env_key}_torch_mode", mode)
        except Exception:
            pass
        try:
            if self.parent() and hasattr(self.parent(), f"_apply_{env_key}_env"):
                getattr(self.parent(), f"_apply_{env_key}_env")()
        except Exception:
            pass

        reuse_note = ""
        torch_cmd = ""
        detect_note = ""
        selected_gpu_tag = ""
        main_info = {}
        mode_satisfies = None
        try:
            from backend.torch_runtime import mode_satisfies
            main_info, _main_py = self._get_main_torch_info_cached(allow_block=True)
        except Exception:
            main_info = {}

        if callable(mode_satisfies) and main_info and mode_satisfies(main_info, mode):
            main_mode = (main_info.get("mode") or mode).upper()
            main_ver = main_info.get("torch_version", "") or "unknown"
            reuse_note = f"已复用主依赖环境 PyTorch（{main_mode}, ver={main_ver}），无需重复安装 torch。"
            if mode == "gpu":
                cv = str(main_info.get("cuda_version") or "").strip().lower()
                if cv.startswith("cu"):
                    selected_gpu_tag = cv
        else:
            extra_index = " --extra-index-url https://pypi.org/simple"
            if mode == "gpu":
                gpu_plan = self._detect_torch_gpu_plan(allow_block=True)
                detect_note = getattr(self, "_cuda_detect_note", "")
                if gpu_plan:
                    selected_gpu_tag = str(gpu_plan.get("tag", "") or "")
                    torch_cmd = (
                        f"\"{pyexe}\" -m pip install "
                        f"torch=={gpu_plan['torch']} torchvision=={gpu_plan['vision']} torchaudio=={gpu_plan['audio']} "
                        f"--index-url https://download.pytorch.org/whl/{gpu_plan['tag']}{extra_index}"
                    )
                else:
                    torch_cmd = ""
            else:
                cpu_plan = self._torch_cpu_plan()
                torch_cmd = (
                    f"\"{pyexe}\" -m pip install "
                    f"torch=={cpu_plan['torch']} torchvision=={cpu_plan['vision']} torchaudio=={cpu_plan['audio']} "
                    f"--index-url https://download.pytorch.org/whl/cpu{extra_index}"
                )
                detect_note = "使用 CPU 版本"

        if mode == "gpu" and not selected_gpu_tag:
            try:
                gpu_plan = self._detect_torch_gpu_plan(allow_block=True)
                if gpu_plan:
                    selected_gpu_tag = str(gpu_plan.get("tag", "") or "")
            except Exception:
                pass

        if mode == "gpu" and not reuse_note and not torch_cmd:
            note = detect_note or getattr(self, "_cuda_detect_note", "") or "未检测到可适配 GPU 版本"
            title = "CUDA 版本不支持" if "低于 11.8" in note else "CUDA 未检测到"
            self._show_info(title, f"{note}。请先安装 CUDA Toolkit，或改装 CPU 版本。", "warning")
            return

        model_cmd = ""
        shared_site_hint = ""
        if not torch_cmd:
            try:
                shared_site_hint = self._resolve_shared_torch_site_for_mode(mode)
            except Exception:
                shared_site_hint = ""
        model_cmd = "\n".join(self._pix2text_install_steps(pyexe, mode, shared_site_hint, selected_gpu_tag))

        cmd_parts = []
        if torch_cmd:
            cmd_parts.append(torch_cmd)
        if include_model and model_cmd:
            cmd_parts.append(model_cmd)
        full_cmd = "\n".join(cmd_parts) if cmd_parts else self._shared_torch_verify_cmd(pyexe, env_key, mode)

        if mode == "gpu" and getattr(self, "_cuda_detect_note", "") and not detect_note:
            detect_note = self._cuda_detect_note
        detect_prefix = f"CUDA 检测: {detect_note}\n\n" if detect_note else ""
        reuse_prefix = (reuse_note + "\n\n") if reuse_note else ""
        def _short(line: str, n: int = 92) -> str:
            line = (line or "").strip()
            return (line[: n - 3] + "...") if len(line) > n else line
        def _preview_cmd() -> str:
            model_lines = [ln for ln in (model_cmd or "").splitlines() if ln.strip()]
            out = []
            if torch_cmd:
                out.append("1) PyTorch 安装/切换")
                out.append(f"   {_short(torch_cmd)}")
            if include_model and model_lines:
                idx = 2 if torch_cmd else 1
                out.append(f"{idx}) {env_key} 模型安装与校验（共 {len(model_lines)} 步）")
                head = min(2, len(model_lines))
                for i in range(head):
                    out.append(f"   - {_short(model_lines[i])}")
                if len(model_lines) > head:
                    out.append(f"   - ... 其余 {len(model_lines) - head} 步已省略（复制后可见完整命令）")
            if not out:
                out.append(_short(full_cmd))
            return "\n".join(out)
        preview_cmd = _preview_cmd()
        if torch_cmd:
            lead_msg = f"将在主依赖环境安装 {mode.upper()} 版 PyTorch：\n\n"
        elif include_model and model_cmd:
            lead_msg = "当前无需安装 torch，仅需执行模型安装/校验：\n\n"
        else:
            lead_msg = "当前无需安装 torch，仅需执行共享 torch 校验：\n\n"
        msg = (
            f"{reuse_prefix}{detect_prefix}"
            + lead_msg
            +
            f"{preview_cmd}\n\n"
            "安装完成后请重新检测。\n"
            "提示：弹窗仅显示预览，完整命令会复制到剪贴板。"
        )
        dlg = MessageBox("安装 PyTorch", msg, self)
        dlg.yesButton.setText("复制命令并打开终端")
        dlg.cancelButton.setText("仅复制命令")
        def _do_copy(open_terminal: bool):
            try:
                # Ensure CRLF for Windows cmd paste (Win10 console is sensitive to LF-only).
                cmd_clip = full_cmd.replace("\r\n", "\n").replace("\n", "\r\n")
                pyperclip.copy(cmd_clip)
            except Exception:
                pass
            if open_terminal:
                self._open_terminal(env_key=env_key)
            try:
                dlg.close()
            except Exception:
                pass
        dlg.yesButton.clicked.connect(lambda: _do_copy(True))
        dlg.cancelButton.clicked.connect(lambda: _do_copy(False))
        dlg.exec()
        self._schedule_env_torch_probe(env_key)
    def _reinstall_env_torch(self, env_key: str):
        items = ["CPU", "GPU"]
        dlg = QInputDialog(self)
        dlg.setWindowTitle("重装 PyTorch")
        dlg.setLabelText("选择要重装的版本:")
        dlg.setComboBoxItems(items)
        dlg.setComboBoxEditable(False)
        dlg.setTextValue(items[0])
        dlg.setWindowFlags(
            (
                dlg.windowFlags()
                | Qt.WindowType.CustomizeWindowHint
                | Qt.WindowType.WindowTitleHint
                | Qt.WindowType.WindowCloseButtonHint
                | Qt.WindowType.WindowSystemMenuHint
            )
            & ~Qt.WindowType.WindowMinimizeButtonHint
            & ~Qt.WindowType.WindowMaximizeButtonHint
            & ~Qt.WindowType.WindowMinMaxButtonsHint
            & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        dlg.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, False)
        dlg.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        dlg.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, True)
        dlg.setFixedSize(dlg.sizeHint())
        if dlg.exec() != int(QDialog.DialogCode.Accepted):
            return
        choice = dlg.textValue()
        mode = "gpu" if choice == "GPU" else "cpu"
        self._install_env_torch(env_key, mode, include_model=False)

    def _init_model_combo(self):
        # 初始化模型下拉框的选择状态
        current = "pix2text"
        if self.parent() and hasattr(self.parent(), "desired_model"):
            current = self.parent().desired_model
        elif self.parent() and hasattr(self.parent(), "cfg"):
            current = self.parent().cfg.get("desired_model", current)
        if not current and self.parent() and hasattr(self.parent(), "current_model"):
            current = self.parent().current_model
        if current and str(current).startswith("pix2text"):
            current_key = "pix2text"
        else:
            current_key = current
        for i, (key, _) in enumerate(self._model_options):
            if key == current_key:
                self.model_combo.setCurrentIndex(i)
                break
        self._init_pix2text_pyexe()
        self._schedule_pix2text_pkg_probe()
        self._schedule_env_torch_probe("pix2text")
        self._init_pix2text_mode()
        self._init_external_model_config()
        self._update_pix2text_visibility()
    def _on_model_combo_changed(self, index: int):
        # 模型下拉框选择变化
        if getattr(self, "_model_selection_syncing", False):
            return
        if index < 0 or index >= len(self._model_options):
            return
        key, _ = self._model_options[index]
        if key == "external_model":
            self.select_model("external_model")
        elif self._is_pix2text_ready():
            mode_key = self._get_pix2text_mode_key()
            self.select_model(self._pix2text_mode_to_model(mode_key))
        else:
            # 触发加载/提示，但保持 UI 选择在 pix2text
            self.select_model("pix2text")
        self._update_model_desc()
        self._update_pix2text_visibility()
    def _init_pix2text_pyexe(self):
        pyexe = (os.environ.get("LATEXSNIPPER_PYEXE", "") or "").strip()
        if not pyexe or not os.path.exists(pyexe):
            pyexe = sys.executable
        self.pix2text_pyexe_input.setText(pyexe)
        if self.parent() and hasattr(self.parent(), "cfg"):
            self.parent().cfg.set("pix2text_pyexe", pyexe)
    def _init_pix2text_mode(self):
        mode = "formula"
        if self.parent() and hasattr(self.parent(), "cfg"):
            mode = self.parent().cfg.get("pix2text_mode", "formula")
        for i in range(self.pix2text_mode_combo.count()):
            if self.pix2text_mode_combo.itemData(i) == mode:
                prev = self.pix2text_mode_combo.blockSignals(True)
                self.pix2text_mode_combo.setCurrentIndex(i)
                self.pix2text_mode_combo.blockSignals(prev)
                break
    def _pix2text_mode_to_model(self, mode_key: str) -> str:
        mapping = {
            "formula": "pix2text",
            "mixed": "pix2text_mixed",
            "text": "pix2text_text",
            "page": "pix2text_page",
            "table": "pix2text_table",
        }
        return mapping.get(mode_key, "pix2text")
    def _get_pix2text_mode_key(self) -> str:
        idx = self.pix2text_mode_combo.currentIndex()
        if idx >= 0:
            key = self.pix2text_mode_combo.itemData(idx)
            if key:
                return key
        return "formula"
    def _is_pix2text_selected(self) -> bool:
        idx = self.model_combo.currentIndex()
        if idx >= 0 and idx < len(self._model_options):
            key, _ = self._model_options[idx]
            return key == "pix2text"
        return False
    def _is_external_model_selected(self) -> bool:
        idx = self.model_combo.currentIndex()
        if idx >= 0 and idx < len(self._model_options):
            key, _ = self._model_options[idx]
            return key == "external_model"
        return False
    def _is_pix2text_ready(self) -> bool:
        # only mark ready after pix2text package is installed
        if getattr(self, "_pix2text_pkg_ready", False):
            return True
        return False
    def _on_pix2text_mode_changed(self, index: int):
        if index < 0:
            return
        mode_key = self.pix2text_mode_combo.itemData(index)
        if self.parent() and hasattr(self.parent(), "cfg"):
            self.parent().cfg.set("pix2text_mode", mode_key)
        if not self._is_pix2text_selected():
            return
        if self._is_pix2text_ready():
            self.select_model(self._pix2text_mode_to_model(mode_key))
    def _update_pix2text_visibility(self):
        key = None
        idx = self.model_combo.currentIndex()
        if idx >= 0 and idx < len(self._model_options):
            key, _ = self._model_options[idx]
        visible = (key == "pix2text")
        external_visible = (key == "external_model")
        ready = self._is_pix2text_ready()
        pyexe = self.pix2text_pyexe_input.text().strip()
        pyexe_exists = bool(pyexe and Path(pyexe).exists())
        try:
            self.pix2text_env_widget.setVisible(visible)
            self.pix2text_env_hint.setVisible(visible)
            self.pix2text_torch_status.setVisible(visible)
            if self.pix2text_torch_btn_row is not None:
                self.pix2text_torch_btn_row.setVisible(visible)
            if self.pix2text_dl_widget is not None:
                self.pix2text_dl_widget.setVisible(visible)
            # 识别类型始终可见（便于用户预先选择）
            self.pix2text_mode_widget.setVisible(visible)
            self.external_model_widget.setVisible(external_visible)
            if visible:
                if not pyexe_exists:
                    self.pix2text_env_hint.setText("⚠️ 主依赖环境未就绪，请先运行依赖向导。")
                elif not ready:
                    self.pix2text_env_hint.setText("⚠️ pix2text 未部署：请先打开【依赖管理向导】安装依赖。")
                else:
                    self.pix2text_env_hint.setText("💡 pix2text 已部署，可选择识别类型。")
            if external_visible:
                self._update_external_model_status()
        except Exception:
            pass
    def _init_render_engine(self):
        """初始化渲染引擎选择"""
        try:
            from backend.latex_renderer import _latex_settings, LaTeXRenderer
            if _latex_settings:
                mode = _latex_settings.get_render_mode()
                self.render_engine_combo.currentIndexChanged.disconnect(self._on_render_engine_changed)
                # 根据 _render_modes 查找对应的索引
                if mode in self._render_modes:
                    index = self._render_modes.index(mode)
                    self.render_engine_combo.setCurrentIndex(index)
                else:
                    # 默认选择自动检测
                    self.render_engine_combo.setCurrentIndex(0)
                self.render_engine_combo.currentIndexChanged.connect(self._on_render_engine_changed)
                current_index = self.render_engine_combo.currentIndex()
                if current_index >= 0 and current_index < len(self._render_modes):
                    engine = self._render_modes[current_index]
                    is_latex = engine.startswith("latex_")
                    self.latex_options_widget.setVisible(is_latex)
                    # LaTeX 模式时尝试自动检测
                    if is_latex and not _latex_settings.get_latex_path():
                        renderer = LaTeXRenderer()
                        if renderer.is_available():
                            self.latex_path_input.setText(renderer.latex_cmd)
                            _latex_settings.set_latex_path(renderer.latex_cmd)
                            _latex_settings.save()
        except Exception as e:
            print(f"[WARN] 初始化渲染引擎失败: {e}")
    def _on_render_engine_changed(self, index: int):
        """渲染引擎改变 - 立即切换，不在主线程做重型验证。"""
        if index < 0:
            return
        # 从 _render_modes 列表获取对应的引擎数据
        if index < 0 or index >= len(self._render_modes):
            print(f"[WARN] 渲染引擎索引无效: {index}")
            return
        engine = self._render_modes[index]
        # 显示/隐藏 LaTeX 选项
        is_latex = engine.startswith("latex_")
        self.latex_options_widget.setVisible(is_latex)
        if is_latex:
            self._sync_latex_path_for_engine(engine)
            latex_path = self.latex_path_input.text().strip()
            if not latex_path:
                self._show_notification("warning", "LaTeX 路径未配置", "已切换引擎。请点击“自动检测”或手动选择路径，再点“验证路径”。")

        # 无论是否 LaTeX，引擎切换都立即保存；耗时验证由“验证路径”按钮触发。
        self._save_render_mode(engine)
    def _load_latex_settings(self):
        """加载 LaTeX 设置"""
        try:
            from backend.latex_renderer import _latex_settings
            if _latex_settings:
                latex_path = _latex_settings.get_latex_path()
                if latex_path:
                    self.latex_path_input.setText(latex_path)
        except Exception as e:
            print(f"[WARN] 加载 LaTeX 设置失败: {e}")
    def _on_latex_path_changed(self):
        """LaTeX 路径改变 - 清除验证状态"""
        if getattr(self, "_latex_test_in_progress", False):
            return
        self.btn_test_latex.setText("验证路径")
        self.btn_test_latex.setEnabled(True)
    def _browse_latex_path(self):
        """浏览 LaTeX 路径"""
        from PyQt6.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 pdflatex 或 xelatex 可执行文件",
            "",
            "可执行文件 (pdflatex.exe xelatex.exe);;所有文件 (*.*)"
        )
        if file_path:
            self.latex_path_input.setText(file_path)
            self._save_latex_settings()
    def _detect_latex(self):
        """异步自动检测 LaTeX（同时检测 pdflatex/xelatex）。"""
        if getattr(self, "_latex_detect_in_progress", False):
            return

        self._latex_detect_in_progress = True
        self.btn_detect_latex.setText("检测中...")
        self.btn_detect_latex.setEnabled(False)

        # 检测偏好以“当前渲染引擎选择”为准；非 LaTeX 模式时按当前路径推断。
        current_engine = ""
        idx = self.render_engine_combo.currentIndex()
        if 0 <= idx < len(self._render_modes):
            current_engine = self._render_modes[idx]
        if current_engine == "latex_xelatex":
            selected_compiler = "xelatex"
        elif current_engine == "latex_pdflatex":
            selected_compiler = "pdflatex"
        else:
            base = os.path.basename((self.latex_path_input.text() or "").strip()).lower()
            selected_compiler = "xelatex" if base == "xelatex.exe" else "pdflatex"
        current_path = self.latex_path_input.text().strip()

        def worker(preferred: str, current: str):
            candidates = {
                "pdflatex": (shutil.which("pdflatex") or "").strip(),
                "xelatex": (shutil.which("xelatex") or "").strip(),
            }

            # 若 PATH 未命中，尝试从当前路径目录推断同级编译器。
            try:
                if current:
                    base_dir = os.path.dirname(current)
                    if base_dir and os.path.isdir(base_dir):
                        pdflatex_exe = os.path.join(base_dir, "pdflatex.exe")
                        xelatex_exe = os.path.join(base_dir, "xelatex.exe")
                        if (not candidates["pdflatex"]) and os.path.exists(pdflatex_exe):
                            candidates["pdflatex"] = pdflatex_exe
                        if (not candidates["xelatex"]) and os.path.exists(xelatex_exe):
                            candidates["xelatex"] = xelatex_exe
            except Exception:
                pass

            chosen = ""
            if candidates.get(preferred):
                chosen = candidates[preferred]
            elif candidates.get("pdflatex"):
                chosen = candidates["pdflatex"]
            elif candidates.get("xelatex"):
                chosen = candidates["xelatex"]

            pd = candidates.get("pdflatex") or "未找到"
            xe = candidates.get("xelatex") or "未找到"
            detail = f"pdflatex: {pd}\nxelatex: {xe}"
            self.latex_auto_detect_done.emit(bool(chosen), chosen, detail)

        import threading
        threading.Thread(target=worker, args=(selected_compiler, current_path), daemon=True).start()

    def _on_latex_auto_detect_done(self, ok: bool, latex_path: str, detail: str):
        self._latex_detect_in_progress = False
        self.btn_detect_latex.setText("自动检测")
        self.btn_detect_latex.setEnabled(True)

        if ok:
            self.latex_path_input.setText(str(latex_path or ""))
            self._save_latex_settings()
            self._show_notification("success", "检测成功", detail)
        else:
            self._show_notification("warning", "检测失败", f"未检测到 LaTeX。\n\n{detail}")
    def _save_latex_settings(self):
        """保存 LaTeX 设置"""
        try:
            from backend.latex_renderer import _latex_settings
            if _latex_settings:
                latex_path = self.latex_path_input.text().strip()
                mode = "auto"
                idx = self.render_engine_combo.currentIndex()
                if 0 <= idx < len(self._render_modes):
                    mode = self._render_modes[idx]
                if mode == "latex_xelatex":
                    use_xelatex = True
                elif mode == "latex_pdflatex":
                    use_xelatex = False
                else:
                    use_xelatex = os.path.basename(latex_path).lower() == "xelatex.exe"
                if latex_path:
                    _latex_settings.set_latex_path(latex_path)
                    _latex_settings.settings["use_xelatex"] = use_xelatex
                    print(f"[LaTeX] 设置已保存: {latex_path}")
        except Exception as e:
            print(f"[WARN] 保存 LaTeX 设置失败: {e}")
    def _test_latex_path(self):
        """异步测试 LaTeX 路径，避免阻塞主线程 UI。"""
        latex_path = self.latex_path_input.text().strip()
        if not latex_path:
            self._show_notification("error", "路径为空", "请输入 LaTeX 路径或点击自动检测")
            return False
        if getattr(self, "_latex_test_in_progress", False):
            return False

        current_index = self.render_engine_combo.currentIndex()
        engine = self._render_modes[current_index] if 0 <= current_index < len(self._render_modes) else "auto"
        self._latex_test_in_progress = True
        self.btn_test_latex.setText("验证中...")
        self.btn_test_latex.setEnabled(False)

        def worker(path_value: str, engine_value: str):
            from backend.latex_renderer import LaTeXRenderer

            ok = False
            title = "验证失败"
            message = "无法用该路径渲染公式，请检查安装"
            try:
                renderer = LaTeXRenderer(path_value)
                if not renderer.is_available():
                    title = "路径无效"
                    message = "找不到 LaTeX 可执行文件"
                else:
                    print(f"[LaTeX] 测试路径: {path_value}")
                    test_svg = renderer.render_to_svg(r"\frac{1}{2} + \frac{1}{3} = \frac{5}{6}")
                    if test_svg and len(test_svg) > 100:
                        ok = True
                        title = "验证成功"
                        message = "LaTeX 环境已就绪"
            except Exception as e:
                print(f"[ERROR] LaTeX 验证失败: {e}")
                title = "验证出错"
                message = str(e)[:100]
            self.latex_path_test_done.emit(bool(ok), str(title), str(message), str(engine_value), str(path_value))

        import threading

        threading.Thread(target=worker, args=(latex_path, engine), daemon=True).start()
        return True

    def _on_latex_path_test_done(self, ok: bool, title: str, message: str, engine: str, tested_path: str):
        self._latex_test_in_progress = False
        if ok:
            self.btn_test_latex.setText("✓ 已验证")
            self.btn_test_latex.setEnabled(False)
            # 若用户在验证期间未改路径，则直接保存；改过也保持显示验证成功状态。
            try:
                if self.latex_path_input.text().strip() == (tested_path or "").strip():
                    self._save_latex_settings()
            except Exception:
                pass
            compiler = "xelatex" if os.path.basename((tested_path or "").strip()).lower() == "xelatex.exe" else "pdflatex"
            self._show_notification("success", title or "验证成功", f"已验证编译器: {compiler}\n路径: {tested_path or ''}")
            return
        self.btn_test_latex.setText("验证路径")
        self.btn_test_latex.setEnabled(True)
        self._show_notification("error", title or "验证失败", message or "无法用该路径渲染公式，请检查安装")
    def _show_notification(self, level: str, title: str, message: str):
        """显示浮动通知
        Args:
            level: 'success', 'warning', 'error', 'info'
            title: 标题
            message: 消息内容
        """
        try:
            from qfluentwidgets import InfoBar, InfoBarPosition
            # 根据等级调用对应的方法
            if level == "success":
                InfoBar.success(
                    title=title,
                    content=message,
                    orient=None,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=2000,
                    parent=self
                )
            elif level == "warning":
                InfoBar.warning(
                    title=title,
                    content=message,
                    orient=None,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=2000,
                    parent=self
                )
            elif level == "error":
                InfoBar.error(
                    title=title,
                    content=message,
                    orient=None,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=2000,
                    parent=self
                )
            else:
                InfoBar.info(
                    title=title,
                    content=message,
                    orient=None,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=2000,
                    parent=self
                )
        except Exception as e:
            print(f"[WARN] 显示通知失败: {e}")
            print(f"[INFO] {title}: {message}")
    def _save_render_mode(self, engine: str):
        """保存渲染引擎选择"""
        try:
            from backend.latex_renderer import _latex_settings
            if _latex_settings:
                _latex_settings.set_render_mode(engine)
                print(f"[Render] 已切换渲染引擎: {engine}")
                # 显示成功信息（InfoBar 浮动提示，替代 MessageBox）
                mode_names = {
                    "auto": "自动检测（MathJax + CDN）",
                    "mathjax_local": "本地 MathJax",
                    "mathjax_cdn": "CDN MathJax",
                    "latex_pdflatex": "LaTeX + pdflatex",
                    "latex_xelatex": "LaTeX + xelatex"
                }
                if engine in mode_names:
                    self._show_notification(
                        "success",
                        "切换成功",
                        f"已切换到: {mode_names[engine]}"
                    )
        except Exception as e:
            print(f"[ERROR] 保存渲染模式失败: {e}")
    def _update_model_desc(self):
        # 更新模型说明
        index = self.model_combo.currentIndex()
        if index < 0:
            return
        key, _ = self._model_options[index]
        descriptions = {
            "pix2text": "内置识别模型，支持公式/混合/文字/整页/表格与 PDF 识别。",
            "external_model": "连接本地多模态 OCR / VLM 接口，适合接入 Qwen、GLM-OCR、PaddleOCR-VL、Ollama 等本地服务。",
        }
        desc = descriptions.get(key, "")
        if key == "pix2text":
            desc += "\n提示：pix2text 依赖由主环境统一管理。"
        elif key == "external_model":
            desc += "\n提示：支持本地和部分线上接口。必填：协议、Base URL、模型名；选填：API Key、超时、提示词。"
        self.lbl_model_desc.setText(desc)
    def _open_terminal(self, env_key: str | None = None):
        if isinstance(env_key, bool):
            env_key = None
        import subprocess
        import os
        from qfluentwidgets import MessageBox, InfoBar, InfoBarPosition
        if env_key is None:
            env_key = self._get_terminal_env_key()
        # 统一只打开主环境终端。
        env_key = "main"
        try:
            _dbg_text = self.terminal_env_combo.currentText()
        except Exception:
            _dbg_text = ""
        try:
            _dbg_idx = self.terminal_env_combo.currentIndex()
        except Exception:
            _dbg_idx = -1
        print(f"[DEBUG] Terminal select: text={_dbg_text!r} idx={_dbg_idx} env_key={env_key}")
        cfg = self.parent().cfg if (self.parent() and hasattr(self.parent(), "cfg")) else None
        def _get_pyexe(key: str) -> str:
            return os.environ.get("LATEXSNIPPER_PYEXE", sys.executable)
        pyexe = _get_pyexe(env_key)
        print(f"[DEBUG] Terminal pyexe initial: {pyexe}")
        if not pyexe or not os.path.exists(pyexe):
            pyexe = _get_pyexe("main")
            if not pyexe or not os.path.exists(pyexe):
                pyexe = sys.executable
        pyexe_dir = os.path.dirname(pyexe)
        scripts_dir = os.path.join(pyexe_dir, "Scripts")
        venv_dir = pyexe_dir
        env_name = {
            "main": "主环境",
        }.get(env_key, "主环境")
        msg = MessageBox(
            "打开环境终端",
            "是否以管理员模式打开终端？\n\n"
            "- 管理员：推荐用于修复权限问题\n"
            "- 普通：快速打开，可能遇到权限错误\n"
            "- ESC：取消",
            self
        )
        msg.yesButton.setText("管理员")
        msg.cancelButton.setText("普通")
        esc_pressed = [False]
        from PyQt6.QtCore import Qt as QtCore_Qt
        from PyQt6.QtGui import QKeyEvent
        original_keyPressEvent = msg.keyPressEvent
        def custom_keyPressEvent(event: QKeyEvent):
            if event.key() == QtCore_Qt.Key.Key_Escape:
                esc_pressed[0] = True
                msg.close()
            else:
                original_keyPressEvent(event)
        msg.keyPressEvent = custom_keyPressEvent
        result = msg.exec()
        if esc_pressed[0]:
            return
        as_admin = result
        env_desc = "主环境（程序 / pix2text / 核心依赖）"
        shared_site_for_terminal = ""
        try:
            mode_pref = "auto"
            if cfg:
                mode_pref = (cfg.get("pix2text_torch_mode", "auto") or "auto").strip().lower()
            # 终端入口使用缓存，避免首次打开卡在 CUDA/torch 探测。
            shared_site_for_terminal = self._resolve_shared_torch_site_for_mode(mode_pref, allow_block=False)
        except Exception:
            shared_site_for_terminal = ""
        gpu_plan = self._detect_torch_gpu_plan(allow_block=False)
        cpu_plan = self._torch_cpu_plan()
        gpu_cmd = ""
        if gpu_plan:
            gpu_cmd = (
                f"pip install torch=={gpu_plan['torch']} torchvision=={gpu_plan['vision']} "
                f"torchaudio=={gpu_plan['audio']} --index-url https://download.pytorch.org/whl/{gpu_plan['tag']}"
            )
        gpu_onnx_cmd = f"pip install {self._onnxruntime_gpu_spec_for_tag(gpu_plan['tag'] if gpu_plan else None)}"
        cpu_onnx_cmd = f"pip install {self._onnxruntime_cpu_spec()}"
        cpu_cmd = (
            f"pip install torch=={cpu_plan['torch']} torchvision=={cpu_plan['vision']} "
            f"torchaudio=={cpu_plan['audio']} --index-url https://download.pytorch.org/whl/cpu"
        )
        help_lines = [
            "echo.",
            "echo ================================================================================",
            f"echo                        LaTeXSnipper Terminal - {env_name}",
            "echo ================================================================================",
            "echo.",
            f"echo [*] Env: {env_desc}",
            f"echo [*] Python: {pyexe_dir}",
            "echo [*] pip/python will use this env",
            "echo.",
            "echo [Model Policy]",
            "echo   - built-in dependency wizard manages the pix2text path",
            "echo   - external_model uses independently deployed local/online services",
            "echo   - use unified main dependency env",
            "echo   - CPU/GPU switch only changes torch + onnxruntime",
            f"echo   - shared torch site: {shared_site_for_terminal or 'not injected'}",
            "echo.",
            "echo [Version Fix]",
            "echo   pip install protobuf==4.25.8",
            "echo.",
            "echo [PyTorch GPU]",
            "echo   nvcc --version",
            f"echo   {gpu_cmd if gpu_cmd else 'CUDA < 11.8 or not detected; GPU command unavailable'}",
            "echo.",
            "echo [PyTorch CPU]",
            f"echo   {cpu_cmd}",
            "echo.",
            "echo [ONNX Runtime]",
            f"echo   {gpu_onnx_cmd}",
            f"echo   {cpu_onnx_cmd}",
            "echo.",
            "echo [Model]",
            "echo   # Step-by-step install (stable order)",
            "echo   pip install -U pip setuptools wheel --default-timeout 180 --retries 15 --prefer-binary --extra-index-url https://pypi.org/simple",
            "echo   pip uninstall -y optimum optimum-onnx optimum-intel",
            "echo   pip install -U \"transformers==4.55.4\" \"tokenizers==0.21.4\" --default-timeout 180 --retries 15 --prefer-binary --extra-index-url https://pypi.org/simple",
            "echo   pip install -U \"optimum-onnx>=0.0.3\" --default-timeout 180 --retries 15 --prefer-binary --extra-index-url https://pypi.org/simple",
            "echo   pip install -U \"pix2text==1.1.6\" --default-timeout 180 --retries 15 --prefer-binary --extra-index-url https://pypi.org/simple",
            "echo   pip install -U \"pymupdf~=1.23.0\" --default-timeout 180 --retries 15 --prefer-binary --extra-index-url https://pypi.org/simple",
            "echo   python -c \"import os,sys; import os as _o; import importlib.util as _iu; s=(os.environ.get('PIX2TEXT_SHARED_TORCH_SITE','') or os.environ.get('LATEXSNIPPER_SHARED_TORCH_SITE','') or '').strip(); added=(bool(s) and _o.path.isdir(s) and s not in sys.path); (sys.path.insert(0,s) if added else None); tl=(_o.path.join(s,'torch','lib') if s else ''); (_o.add_dll_directory(tl) if (tl and _o.path.isdir(tl) and hasattr(_o,'add_dll_directory')) else None); _o.environ['PATH']=((tl+_o.pathsep+_o.environ.get('PATH','')) if (tl and _o.path.isdir(tl)) else _o.environ.get('PATH','')); import torch; import torchvision; (__import__('torchaudio') if _iu.find_spec('torchaudio') else None); (sys.path.remove(s) if (added and s in sys.path) else None); from pix2text import Pix2Text; print('pix2text ok')\"",
            "echo.",
        ]
        help_lines += [
            "echo [Diagnostics]",
            "echo   pip list",
            "echo   pip check",
            "echo   python -c \"import torch; print('CUDA:', torch.cuda.is_available(), 'Ver:', torch.version.cuda)\"",
            "echo   nvidia-smi",
            "echo   nvcc --version",
            "echo.",
            "echo [Cache Clean]",
            "echo   pip cache purge",
            "echo.",
            "echo ================================================================================",
            "echo.",
        ]
        help_text = "\n".join(help_lines) + "\n"
        shared_env_lines = ""
        if shared_site_for_terminal:
            shared_env_lines = (
                f'set "PIX2TEXT_SHARED_TORCH_SITE={shared_site_for_terminal}"\n'
                'set "LATEXSNIPPER_SHARED_TORCH_SITE="\n'
            )
        else:
            shared_env_lines = (
                'set "PIX2TEXT_SHARED_TORCH_SITE="\n'
                'set "LATEXSNIPPER_SHARED_TORCH_SITE="\n'
            )
        try:
            if as_admin:
                import tempfile
                batch_content = "@echo off\n" \
                    + f'cd /d "{venv_dir}"\n' \
                    + f'set "PATH={pyexe_dir};{scripts_dir};%PATH%"\n' \
                    + shared_env_lines \
                    + help_text
                with tempfile.NamedTemporaryFile(mode="w", suffix=".bat", delete=False, encoding="mbcs", newline="\r\n") as f:
                    f.write(batch_content)
                    batch_path = f.name
                import ctypes
                ctypes.windll.shell32.ShellExecuteW(
                    None, "runas", "cmd.exe", f"/k \"{batch_path}\"", None, 1
                )
                self._show_info("终端已打开", "已弹出 UAC 授权提示。", "success")
            else:
                import tempfile
                batch_content_normal = "@echo off\n" \
                    + f'cd /d "{venv_dir}"\n' \
                    + f'set "PATH={pyexe_dir};{scripts_dir};%PATH%"\n' \
                    + shared_env_lines \
                    + help_text
                with tempfile.NamedTemporaryFile(mode="w", suffix=".bat", delete=False, encoding="mbcs", newline="\r\n") as f:
                    f.write(batch_content_normal)
                    batch_path = f.name
                subprocess.Popen(
                    ["cmd.exe", "/k", batch_path],
                    cwd=venv_dir,
                    creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
                )
                self._show_info("终端已打开", "已以普通模式打开。", "success")
        except Exception as e:
            self._show_info("终端打开失败", str(e), "error")

    def _resolve_pix2text_cache_dir(self) -> str:
        # 快速路径：避免每次点击都拉起 python 子进程，防止 UI 卡顿。
        env_home = (os.environ.get("PIX2TEXT_HOME", "") or "").strip()
        if env_home:
            return os.path.normpath(env_home)
        appdata = (os.environ.get("APPDATA", "") or "").strip()
        if appdata:
            return os.path.normpath(os.path.join(appdata, "pix2text"))
        return os.path.normpath(os.path.expanduser("~/.pix2text"))

    def _open_pix2text_cache_dir(self):
        path = self._resolve_pix2text_cache_dir()
        try:
            os.makedirs(path, exist_ok=True)
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
            self._show_info("已打开", f"pix2text 缓存目录: {path}", "success")
        except Exception as e:
            self._show_info("打开失败", f"无法打开缓存目录: {e}", "error")

    def _open_deps_wizard(self):
        """打开依赖管理向导"""
        from qfluentwidgets import MessageBox
        msg = MessageBox(
            "打开依赖向导",
            "依赖管理向导将以重启后的干净进程打开。\n\n是否立即重启并打开依赖向导？\n• ESC取消操作",
            self
        )
        msg.yesButton.setText("重启并打开")
        msg.cancelButton.setText("取消")

        esc_pressed = [False]
        from PyQt6.QtCore import Qt as QtCore_Qt
        from PyQt6.QtGui import QKeyEvent
        original_keyPressEvent = msg.keyPressEvent

        def custom_keyPressEvent(event: QKeyEvent):
            if event.key() == QtCore_Qt.Key.Key_Escape:
                esc_pressed[0] = True
                msg.close()
            else:
                original_keyPressEvent(event)

        msg.keyPressEvent = custom_keyPressEvent
        result = msg.exec()
        if esc_pressed[0] or not result:
            return
        self._restart_with_wizard()
    def _restart_with_wizard(self):
        """重启程序并打开依赖向导"""
        import subprocess
        import sys
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QCoreApplication, QProcess, QProcessEnvironment
        import os

        argv0 = ""
        try:
            argv0 = QCoreApplication.applicationFilePath() or ""
        except Exception:
            argv0 = ""
        exe_name = os.path.basename(argv0).lower() if argv0 else ""
        if (not argv0) or exe_name in ("python.exe", "pythonw.exe", "python", "pythonw"):
            argv0 = os.path.abspath(sys.argv[0]) if sys.argv else ""
        spawn_argv, env = build_restart_with_wizard_launch(
            python_exe=sys.executable,
            argv0=argv0,
            base_env=os.environ.copy(),
        )
        try:
            # 先释放重资源和实例锁，减少“新进程抢锁失败”概率
            parent = self.parent()
            if parent and hasattr(parent, "prepare_restart"):
                try:
                    parent.prepare_restart()
                except Exception:
                    pass
            try:
                app = QApplication.instance()
                if app:
                    app.processEvents()
            except Exception:
                pass
            started = False
            try:
                program = str(spawn_argv[0])
                arguments = [str(x) for x in spawn_argv[1:]]
                workdir = os.path.dirname(os.path.abspath(arguments[0])) if arguments else os.getcwd()
            except Exception:
                program = ""
                arguments = []
                workdir = os.getcwd()
            try:
                proc_env = QProcessEnvironment.systemEnvironment()
                for k, v in env.items():
                    proc_env.insert(str(k), str(v))
                started = QProcess.startDetached(program, arguments, workdir)
            except Exception:
                started = False
            if not started:
                base_flags = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
                spawn_flags = base_flags | int(_subprocess_creationflags())
                subprocess.Popen(
                    spawn_argv,
                    env=env,
                    creationflags=spawn_flags
                )
            # 关闭当前程序
            QApplication.instance().quit()
        except Exception as e:
            from qfluentwidgets import InfoBar, InfoBarPosition
            InfoBar.error(
                title="重启失败",
                content=f"无法重启程序: {e}",
                parent=self,
                duration=5000,
                position=InfoBarPosition.TOP
            )
    def _show_info(self, title: str, content: str, level: str = "info"):
        """显示 Fluent 浮动提示"""
        from qfluentwidgets import InfoBar, InfoBarPosition
        # 始终浮在设置窗口，避免遮挡主窗口
        parent = self
        func = getattr(InfoBar, level, InfoBar.info)
        func(
            title=title,
            content=content,
            parent=parent,
            duration=4000,
            position=InfoBarPosition.TOP
        )
    def _set_combo_value(self, combo: ComboBox, value: str):
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                prev = combo.blockSignals(True)
                combo.setCurrentIndex(i)
                combo.blockSignals(prev)
                return
    def _set_lineedit_value(self, widget: QLineEdit, value: str):
        prev = widget.blockSignals(True)
        widget.setText(str(value or ""))
        widget.blockSignals(prev)
    def _get_external_combo_value(self, combo: ComboBox, default: str) -> str:
        idx = combo.currentIndex()
        if idx >= 0:
            value = combo.itemData(idx)
            if value is not None:
                return str(value)
        return default
    def _init_external_model_config(self):
        cfg = None
        try:
            if self.parent() and hasattr(self.parent(), "cfg"):
                cfg = self.parent().cfg
        except Exception:
            cfg = None
        config = load_config_from_mapping(cfg or {})
        data = config.to_mapping()
        self._set_combo_value(self.external_provider_combo, data["external_model_provider"])
        self._set_combo_value(self.external_output_combo, data["external_model_output_mode"])
        self._set_combo_value(self.external_prompt_combo, data["external_model_prompt_template"])
        self._set_combo_value(self.external_preset_combo, data["external_model_preset"])
        self._set_lineedit_value(self.external_base_url_input, data["external_model_base_url"])
        self._set_lineedit_value(self.external_model_name_input, data["external_model_model_name"])
        self._set_lineedit_value(self.external_api_key_input, data["external_model_api_key"])
        self._set_lineedit_value(self.external_timeout_input, str(data["external_model_timeout_sec"]))
        self._set_lineedit_value(self.external_custom_prompt_input, data["external_model_custom_prompt"])
        self._set_lineedit_value(self.external_mineru_endpoint_input, data["external_model_mineru_endpoint"])
        self._set_lineedit_value(self.external_mineru_test_endpoint_input, data["external_model_mineru_test_endpoint"])
        self._set_combo_value(self.external_mineru_mode_combo, data["external_model_mineru_mode"])
        self._on_external_preset_changed()
        self._update_external_provider_visibility()
        self._update_external_model_status()
    def _collect_external_model_config(self):
        config = load_config_from_mapping({})
        config.provider = self._get_external_combo_value(self.external_provider_combo, "openai_compatible")
        config.base_url = self.external_base_url_input.text().strip()
        config.model_name = self.external_model_name_input.text().strip()
        config.api_key = self.external_api_key_input.text().strip()
        config.output_mode = self._get_external_combo_value(self.external_output_combo, "latex")
        config.prompt_template = self._get_external_combo_value(self.external_prompt_combo, "ocr_formula_v1")
        config.custom_prompt = self.external_custom_prompt_input.text().strip()
        config.preset = self._get_external_combo_value(self.external_preset_combo, "")
        config.mineru_endpoint = self.external_mineru_endpoint_input.text().strip()
        config.mineru_test_endpoint = self.external_mineru_test_endpoint_input.text().strip()
        config.mineru_mode = self._get_external_combo_value(self.external_mineru_mode_combo, "auto")
        try:
            config.timeout_sec = int((self.external_timeout_input.text() or "60").strip())
        except Exception:
            config.timeout_sec = 60
        return config

    def _external_config_signature(self, config) -> str:
        provider = config.normalized_provider()
        base_url = config.normalized_base_url()
        model_name = config.normalized_model_name()
        mineru_endpoint = config.normalized_mineru_endpoint()
        mineru_mode = config.normalized_mineru_mode()
        return f"{provider}|{base_url}|{model_name}|{mineru_endpoint}|{mineru_mode}"

    def _is_external_required_fields_ready(self, config) -> bool:
        provider = config.normalized_provider()
        if not config.normalized_base_url():
            return False
        if provider == "mineru":
            return bool(config.normalized_mineru_endpoint())
        return bool(config.normalized_model_name())

    def _update_external_provider_visibility(self):
        config = self._collect_external_model_config()
        is_mineru = config.normalized_provider() == "mineru"
        self.external_mineru_endpoint_input.setVisible(is_mineru)
        self.external_mineru_test_endpoint_input.setVisible(is_mineru)
        self.external_mineru_mode_row.setVisible(is_mineru)
        if is_mineru:
            self.external_model_name_input.setPlaceholderText("可选：模型名（MinerU 原生接口通常可留空）")
        else:
            self.external_model_name_input.setPlaceholderText("必填：模型名，例如 qwen2.5vl:7b；必须与服务中的真实名称一致")

    def _on_external_provider_changed(self, *_args):
        self._update_external_provider_visibility()

    def _notify_parent_external_status_changed(self):
        parent = self.parent()
        if parent is None:
            return
        try:
            preferred = ""
            if hasattr(parent, "_get_preferred_model_for_predict"):
                preferred = str(parent._get_preferred_model_for_predict() or "").strip().lower()
            current = str(getattr(parent, "current_model", "") or "").strip().lower()
            if current == "external_model" or preferred == "external_model":
                if hasattr(parent, "set_model_status") and hasattr(parent, "_get_external_model_status_text"):
                    parent.set_model_status(parent._get_external_model_status_text())
                elif hasattr(parent, "refresh_status_label"):
                    parent.refresh_status_label()
        except Exception:
            pass

    def _save_external_model_config(self):
        config = self._collect_external_model_config()
        try:
            parent_cfg = getattr(self.parent(), "cfg", None)
            if parent_cfg is not None:
                for key, value in config.to_mapping().items():
                    parent_cfg.set(key, value)
                current_sig = self._external_config_signature(config)
                tested_sig = str(parent_cfg.get("external_model_last_test_signature", "") or "")
                if tested_sig != current_sig:
                    parent_cfg.set("external_model_last_test_ok", False)
                    parent_cfg.set("external_model_last_test_message", "")
        except Exception:
            pass
        self._update_external_provider_visibility()
        self._update_external_model_status()
        self._notify_parent_external_status_changed()
    def _on_external_config_changed(self, *_args):
        self._save_external_model_config()
    def _on_external_preset_changed(self, *_args):
        preset = get_preset(self._get_external_combo_value(self.external_preset_combo, ""))
        if preset:
            self.external_hint.setText(str(preset.get("hint") or ""))
        else:
            self.external_hint.setText("必填项只有协议、Base URL、模型名。若测试提示 model not found / unknown model，通常就是模型名填写不正确。")
        self._save_external_model_config()
    def _apply_external_preset(self):
        preset = get_preset(self._get_external_combo_value(self.external_preset_combo, ""))
        if not preset:
            self._show_info("未选择预设", "请选择一个推荐预设后再应用。", "warning")
            return
        self._set_combo_value(self.external_provider_combo, str(preset.get("provider") or "openai_compatible"))
        self._set_lineedit_value(self.external_base_url_input, str(preset.get("base_url") or ""))
        self._set_lineedit_value(self.external_model_name_input, str(preset.get("model_name") or ""))
        self._set_combo_value(self.external_output_combo, str(preset.get("output_mode") or "latex"))
        self._set_combo_value(self.external_prompt_combo, str(preset.get("prompt_template") or "ocr_formula_v1"))
        self._set_lineedit_value(self.external_mineru_endpoint_input, str(preset.get("mineru_endpoint") or "/v1/parse"))
        self._set_lineedit_value(self.external_mineru_test_endpoint_input, str(preset.get("mineru_test_endpoint") or "/health"))
        self._set_combo_value(self.external_mineru_mode_combo, str(preset.get("mineru_mode") or "auto"))
        self.external_hint.setText(str(preset.get("hint") or ""))
        self._save_external_model_config()
        self._show_info("预设已应用", "已填入推荐配置，请按你的本地服务实际情况检查模型名。", "success")
    def _test_external_model_connection(self):
        if self._external_test_thread and self._external_test_thread.isRunning():
            self._show_info("测试进行中", "当前已有一个测试连接任务在后台运行。", "warning")
            return
        config = self._collect_external_model_config()
        self._save_external_model_config()
        self.external_test_btn.setEnabled(False)
        self.external_test_btn.setText("测试中...")
        self._update_external_model_status(test_message="正在后台测试连接，请稍候...")

        self._external_test_thread = QThread(self)
        self._external_test_worker = ExternalModelConnectionWorker(config)
        self._external_test_worker.moveToThread(self._external_test_thread)

        def _cleanup():
            try:
                self.external_test_btn.setEnabled(True)
                self.external_test_btn.setText("测试连接")
            except Exception:
                pass
            if self._external_test_worker:
                self._external_test_worker.deleteLater()
                self._external_test_worker = None
            if self._external_test_thread:
                self._external_test_thread.deleteLater()
                self._external_test_thread = None

        def _on_ok(ok: bool, message: str):
            cfg = getattr(self.parent(), "cfg", None)
            if cfg is not None:
                try:
                    cfg.set("external_model_last_test_ok", bool(ok))
                    cfg.set("external_model_last_test_signature", self._external_config_signature(config))
                    cfg.set("external_model_last_test_message", str(message or ""))
                except Exception:
                    pass
            self._update_external_model_status(test_message=message if ok else "测试未通过")
            self._show_info("测试成功", message or "连接成功，本地服务可访问。", "success")
            self._notify_parent_external_status_changed()

        def _on_fail(message: str):
            pretty = self._format_external_test_error(message)
            cfg = getattr(self.parent(), "cfg", None)
            if cfg is not None:
                try:
                    cfg.set("external_model_last_test_ok", False)
                    cfg.set("external_model_last_test_signature", self._external_config_signature(config))
                    cfg.set("external_model_last_test_message", str(pretty or ""))
                except Exception:
                    pass
            self._update_external_model_status(test_message=pretty)
            self._show_info("测试失败", pretty, "error")
            self._notify_parent_external_status_changed()

        self._external_test_thread.started.connect(self._external_test_worker.run)
        self._external_test_worker.finished.connect(_on_ok)
        self._external_test_worker.failed.connect(_on_fail)
        self._external_test_worker.finished.connect(self._external_test_thread.quit)
        self._external_test_worker.failed.connect(self._external_test_thread.quit)
        self._external_test_thread.finished.connect(_cleanup)
        self._external_test_thread.start()
    def _format_external_test_error(self, message: str) -> str:
        text = str(message or "").strip()
        low = text.lower()
        if "model not found" in low or "unknown model" in low or '"error":"model' in low:
            return f"{text}\n提示：模型名填写错误或该模型未在服务中加载。"
        if "401" in low or "unauthorized" in low or "invalid api key" in low:
            return f"{text}\n提示：请检查 API Key 是否必填、是否填写正确。"
        if "404" in low:
            return f"{text}\n提示：请检查 Base URL、协议类型以及服务端路由是否正确。"
        if "timeout" in low:
            return f"{text}\n提示：服务响应较慢，可提高超时或先确认模型是否已完成加载。"
        return text
    def _show_external_model_help(self):
        if self._external_help_window is None:
            self._external_help_window = ExternalModelHelpWindow(self)
            self._external_help_window.destroyed.connect(lambda: setattr(self, "_external_help_window", None))
        self._external_help_window.show()
        self._external_help_window.raise_()
        self._external_help_window.activateWindow()
    def _update_external_model_status(self, test_message: str = ""):
        config = self._collect_external_model_config()
        provider = config.normalized_provider()
        base_url = config.normalized_base_url()
        model_name = config.normalized_model_name()
        cfg = getattr(self.parent(), "cfg", None)
        current_sig = self._external_config_signature(config)
        tested_ok = False
        tested_sig = ""
        saved_message = ""
        if cfg is not None:
            try:
                tested_ok = bool(cfg.get("external_model_last_test_ok", False))
                tested_sig = str(cfg.get("external_model_last_test_signature", "") or "")
                saved_message = str(cfg.get("external_model_last_test_message", "") or "")
            except Exception:
                tested_ok = False
                tested_sig = ""
                saved_message = ""
        if not base_url:
            status = "状态：未配置。必填项缺少 Base URL。"
        elif provider != "mineru" and not model_name:
            status = "状态：未配置。必填项缺少模型名。"
        else:
            provider_label = "MinerU" if provider == "mineru" else ("Ollama" if provider == "ollama" else "OpenAI-compatible")
            if tested_sig == current_sig:
                state_text = "已连接" if tested_ok else "连接失败"
            else:
                state_text = "已配置，尚未测试连接"
            if provider == "mineru":
                status = (
                    f"状态：{state_text}。协议 {provider_label}，路径 {config.normalized_mineru_endpoint()}，"
                    f"模式 {config.normalized_mineru_mode()}"
                )
            else:
                status = f"状态：{state_text}。协议 {provider_label}，模型 {model_name}"
        if test_message:
            status = f"{status}\n最近一次测试：{test_message}"
        elif saved_message and tested_sig == current_sig:
            status = f"{status}\n最近一次测试：{saved_message}"
        self.external_status.setText(status)
    def select_model(self, model_name: str):
        # 只发射信号，由信号连接的 on_model_changed 处理
        self.model_changed.emit(model_name)
        self._update_compute_mode_label()
    def _update_compute_mode_label(self):
        """更新计算模式状态标签"""
        try:
            import torch
            cuda_available = torch.cuda.is_available()
            if cuda_available:
                gpu_name = torch.cuda.get_device_name(0)
                self.lbl_compute_mode.setText(f"🟢 GPU 可用: {gpu_name}")
                self._compute_mode_state = "gpu"
            else:
                self.lbl_compute_mode.setText("🟡 仅 CPU 模式 (未检测到 GPU层依赖)")
                self._compute_mode_state = "cpu"
        except Exception:
            self.lbl_compute_mode.setText("⚪ 计算模式未知")
            self._compute_mode_state = "unknown"
        self.apply_theme_styles(force=True)
    def update_model_selection(self):
        # sync model combo selection state
        if getattr(self, "_model_selection_syncing", False):
            return
        current = "pix2text"
        try:
            if self.parent() and hasattr(self.parent(), "desired_model"):
                current = str(self.parent().desired_model or "pix2text")
            elif self.parent() and hasattr(self.parent(), "cfg"):
                current = str(self.parent().cfg.get("desired_model", current) or current)
        except Exception:
            current = "pix2text"
        target = "external_model" if current == "external_model" else "pix2text"
        self._model_selection_syncing = True
        try:
            for i, (key, _) in enumerate(self._model_options):
                if key == target:
                    self.model_combo.blockSignals(True)
                    self.model_combo.setCurrentIndex(i)
                    self.model_combo.blockSignals(False)
                    break
            self._init_pix2text_mode()
            self._init_external_model_config()
            self._update_model_desc()
            self._update_pix2text_visibility()
        finally:
            self._model_selection_syncing = False
# ---------------- 主窗口 ----------------
from PyQt6.QtCore import Qt

