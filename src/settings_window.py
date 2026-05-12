import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QEvent, QThread
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import (QDialog, QLineEdit, QVBoxLayout, QLabel, QHBoxLayout, QWidget, QCheckBox, QScrollArea, QPlainTextEdit)
from qfluentwidgets import FluentIcon, PushButton, PrimaryPushButton, ComboBox, MessageBox
from runtime.distribution import is_store_distribution
from updater import check_update_dialog
from backend.external_model import (
    ExternalModelConnectionWorker,
    PRESET_ITEMS,
    get_preset,
    load_config_from_mapping,
)
from backend.cuda_runtime_policy import onnxruntime_cpu_spec, onnxruntime_gpu_policy
from core.restart_contract import build_restart_with_wizard_launch


def _resource_path(relative_path: str) -> str:
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


def _apply_app_window_icon(win) -> None:
    try:
        from PyQt6.QtGui import QIcon
        icon_path = _resource_path("assets/icon.ico")
        if icon_path and os.path.exists(icon_path):
            win.setWindowIcon(QIcon(icon_path))
    except Exception:
        pass


def _select_open_file_with_icon(parent, title: str, initial_path: str, filter_: str):
    from PyQt6.QtWidgets import QFileDialog
    dlg = QFileDialog(parent, title, initial_path, filter_)
    dlg.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
    dlg.setFileMode(QFileDialog.FileMode.ExistingFile)
    _apply_app_window_icon(dlg)
    if dlg.exec() != QFileDialog.DialogCode.Accepted:
        return "", ""
    selected = dlg.selectedFiles()
    chosen_filter = dlg.selectedNameFilter()
    return (selected[0] if selected else ""), chosen_filter


def _subprocess_creationflags() -> int:
    if os.name != "nt":
        return 0
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _mathcraft_code_roots() -> list[str]:
    roots: list[Path] = []

    def add(path: str | Path | None) -> None:
        if not path:
            return
        try:
            p = Path(path).resolve()
        except Exception:
            return
        if p.exists() and p not in roots:
            roots.append(p)

    current = Path(__file__).resolve()
    add(current.parent)
    for parent in current.parents:
        add(parent)
        add(parent / "_internal")
        if (parent / "mathcraft_ocr").is_dir() or (parent / "_internal" / "mathcraft_ocr").is_dir():
            break
    meipass = getattr(sys, "_MEIPASS", None)
    add(meipass)
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        add(exe_dir)
        add(exe_dir / "_internal")
    return [str(path) for path in roots]


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


class SettingsWindow(QDialog):
    """Settings window based on QDialog."""
    model_changed = pyqtSignal(str)
    compute_mode_probe_done = pyqtSignal(object, str)
    mathcraft_pkg_probe_done = pyqtSignal(bool)
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
        # Use a wider default size to avoid truncating InfoBar text.
        self.resize(550, 665)
        self.setMinimumWidth(550)
        self.setMinimumHeight(665)
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
        self._mathcraft_pkg_ready = False
        # Cache slow probe results to avoid blocking the UI on repeated clicks.
        self._probe_cache_ttl_sec = 45.0
        self._compute_mode_probe_py = ""
        self._compute_mode_probe_ts = 0.0
        self._compute_mode_probe_info = None
        self._compute_mode_probe_running = False
        self._device_name_cache = {"gpu": "", "cpu": "", "ts": 0.0}
        self._theme_mode_values = ["light", "dark", "auto"]
        # Model selection area.
        lay.addWidget(QLabel("选择识别模型:"))
        # Use a combo box for built-in and external model entries.
        self.model_combo = ComboBox()
        self.model_combo.setFixedHeight(36)
        # Add recognition model options.
        self._model_options = [
            ("mathcraft", "内置模型"),
            ("external_model", "外部模型"),
        ]
        for key, label in self._model_options:
            self.model_combo.addItem(label, userData=key)
        lay.addWidget(self.model_combo)
        # Model description.
        self.lbl_model_desc = QLabel()
        self.lbl_model_desc.setStyleSheet("color: #666; font-size: 11px; padding: 4px;")
        self.lbl_model_desc.setWordWrap(True)
        lay.addWidget(self.lbl_model_desc)
        # MathCraft environment selection.
        self.mathcraft_env_widget = QWidget()
        mathcraft_env_layout = QHBoxLayout(self.mathcraft_env_widget)
        mathcraft_env_layout.setContentsMargins(0, 0, 0, 0)
        mathcraft_env_layout.setSpacing(6)
        mathcraft_env_layout.addWidget(QLabel("MathCraft 运行环境:"))
        self.mathcraft_pyexe_input = QLineEdit()
        self.mathcraft_pyexe_input.setPlaceholderText("使用主依赖环境 python.exe")
        self.mathcraft_pyexe_input.setFixedHeight(30)
        self.mathcraft_pyexe_input.setReadOnly(True)
        mathcraft_env_layout.addWidget(self.mathcraft_pyexe_input)
        lay.addWidget(self.mathcraft_env_widget)
        self.mathcraft_env_hint = QLabel("提示：MathCraft 统一使用主依赖环境。")
        self.mathcraft_env_hint.setStyleSheet("color: #666; font-size: 10px; padding: 2px;")
        self.mathcraft_env_hint.setWordWrap(True)
        lay.addWidget(self.mathcraft_env_hint)
        # Installation and downloads are handled by the dependency wizard; the settings page no longer exposes separate model install/download actions.
        self.mathcraft_dl_widget = None
        self.mathcraft_download_btn = None
        self.mathcraft_open_btn = None
        # MathCraft recognition type; shown only when the built-in model is available.
        self.mathcraft_mode_widget = QWidget()
        mathcraft_mode_layout = QHBoxLayout(self.mathcraft_mode_widget)
        mathcraft_mode_layout.setContentsMargins(0, 0, 0, 0)
        mathcraft_mode_layout.setSpacing(6)
        mathcraft_mode_layout.addWidget(QLabel("MathCraft 识别类型:"))
        self.mathcraft_mode_combo = ComboBox()
        self.mathcraft_mode_combo.setFixedHeight(30)
        self.mathcraft_mode_combo.addItem("公式", userData="formula")
        self.mathcraft_mode_combo.addItem("混合(文字+公式)", userData="mixed")
        self.mathcraft_mode_combo.addItem("纯文字", userData="text")
        self.mathcraft_mode_combo.currentIndexChanged.connect(self._on_mathcraft_mode_changed)
        mathcraft_mode_layout.addWidget(self.mathcraft_mode_combo)
        lay.addWidget(self.mathcraft_mode_widget)
        self.external_model_widget = QWidget()
        external_layout = QVBoxLayout(self.external_model_widget)
        external_layout.setContentsMargins(0, 6, 0, 0)
        external_layout.setSpacing(6)
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
        self.external_mineru_endpoint_input.setPlaceholderText("MinerU 解析接口路径（例如 /file_parse）")
        self.external_mineru_endpoint_input.setFixedHeight(32)
        external_layout.addWidget(self.external_mineru_endpoint_input)
        self.external_mineru_test_endpoint_input = QLineEdit()
        self.external_mineru_test_endpoint_input.setPlaceholderText("MinerU 健康检查路径（例如 /health）")
        self.external_mineru_test_endpoint_input.setFixedHeight(32)
        external_layout.addWidget(self.external_mineru_test_endpoint_input)
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
        self.lbl_compute_mode = QLabel()
        self.lbl_compute_mode.setStyleSheet("color: #666; font-size: 11px; padding: 4px;")
        lay.addWidget(self.lbl_compute_mode)
        self._update_compute_mode_label()
        # Separator.
        lay.addSpacing(12)
        # ============ Appearance Theme Settings ============
        lay.addWidget(QLabel("外观主题:"))
        self.theme_mode_combo = ComboBox()
        self.theme_mode_combo.setFixedHeight(36)
        self.theme_mode_combo.addItem("浅色", userData="light")
        self.theme_mode_combo.addItem("深色", userData="dark")
        self.theme_mode_combo.addItem("跟随系统", userData="auto")
        lay.addWidget(self.theme_mode_combo)
        # ============ Rendering Engine Settings ============
        lay.addWidget(QLabel("公式渲染引擎:"))
        # Render engine selector; use qfluentwidgets ComboBox for consistent styling.
        self.render_engine_combo = ComboBox()
        self.render_engine_combo.setFixedHeight(36)
        # Add items.
        self.render_engine_combo.addItems([
            "自动检测 (MathJax CDN 备选)",
            "本地 MathJax",
            "CDN MathJax",
            "LaTeX + pdflatex",
            "LaTeX + xelatex",
        ])
        # Store the corresponding data.
        self._render_modes = ["auto", "mathjax_local", "mathjax_cdn", "latex_pdflatex", "latex_xelatex"]
        lay.addWidget(self.render_engine_combo)
        # LaTeX options container; shown only when LaTeX is selected.
        self.latex_options_widget = QWidget()
        latex_layout = QVBoxLayout(self.latex_options_widget)
        latex_layout.setContentsMargins(0, 8, 0, 0)
        latex_layout.setSpacing(6)
        # LaTeX path selector.
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
        # LaTeX action buttons.
        latex_btn_layout = QHBoxLayout()
        self.btn_detect_latex = PushButton(FluentIcon.SEARCH, "自动检测")
        self.btn_detect_latex.setFixedHeight(32)
        latex_btn_layout.addWidget(self.btn_detect_latex)
        self.btn_test_latex = PrimaryPushButton("验证路径")
        self.btn_test_latex.setFixedHeight(32)
        latex_btn_layout.addWidget(self.btn_test_latex)
        latex_layout.addLayout(latex_btn_layout)
        # LaTeX description.
        self.lbl_latex_desc = QLabel("💡 需要本地安装 MiKTeX 或 TeX Live，验证通过后才能使用")
        self.lbl_latex_desc.setStyleSheet("color: #666; font-size: 10px; padding: 4px;")
        self.lbl_latex_desc.setWordWrap(True)
        latex_layout.addWidget(self.lbl_latex_desc)
        self.latex_options_widget.setVisible(False)  # Hidden by default.
        lay.addWidget(self.latex_options_widget)
        # Check for updates.
        lay.addWidget(QLabel("检查更新:"))
        update_text = "打开 Microsoft Store 更新" if is_store_distribution() else "检查更新"
        self.btn_update = PushButton(FluentIcon.UPDATE, update_text)
        self.btn_update.setFixedHeight(36)
        lay.addWidget(self.btn_update)
        # Startup behavior.
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
        # Separator.
        lay.addSpacing(8)
        # Advanced action: open terminal; use carefully.
        lay.addWidget(QLabel("高级 (慎用):"))
        terminal_row = QWidget()
        terminal_layout = QHBoxLayout(terminal_row)
        terminal_layout.setContentsMargins(0, 0, 0, 0)
        terminal_layout.setSpacing(6)
        self.terminal_env_combo = ComboBox()
        self.terminal_env_combo.setFixedHeight(36)
        self.terminal_env_combo.addItem("主环境（程序 / MathCraft）", userData="main")
        terminal_layout.addWidget(self.terminal_env_combo)
        self.btn_terminal = PushButton(FluentIcon.COMMAND_PROMPT, "打开环境终端")
        self.btn_terminal.setFixedHeight(36)
        self.btn_terminal.setToolTip("打开所选环境的终端，可手动安装/修复依赖。\n⚠️ 请谨慎操作，错误的命令可能损坏环境！")
        terminal_layout.addWidget(self.btn_terminal)
        lay.addWidget(terminal_row)
        # Dependency management wizard and cache directory.
        deps_row = QWidget()
        deps_row_layout = QHBoxLayout(deps_row)
        deps_row_layout.setContentsMargins(0, 0, 0, 0)
        deps_row_layout.setSpacing(6)
        self.btn_deps_wizard = PushButton(FluentIcon.DEVELOPER_TOOLS, "依赖管理向导")
        self.btn_deps_wizard.setFixedHeight(36)
        self.btn_deps_wizard.setToolTip("打开依赖管理向导，可安装/升级 GPU 加速层、模型依赖等。\n从设置页进入会执行真实依赖校验。")
        deps_row_layout.addWidget(self.btn_deps_wizard, 1)
        self.btn_open_mathcraft_cache = PushButton(FluentIcon.FOLDER, "打开缓存目录")
        self.btn_open_mathcraft_cache.setFixedHeight(36)
        self.btn_open_mathcraft_cache.setToolTip("打开 MathCraft 模型缓存目录（默认位于AppData\\Roaming\\MathCraft\\models）")
        deps_row_layout.addWidget(self.btn_open_mathcraft_cache, 1)
        lay.addWidget(deps_row)
        # Stretch spacer.
        lay.addStretch()
        # Connect signals.
        self.model_combo.currentIndexChanged.connect(self._on_model_combo_changed)
        self.compute_mode_probe_done.connect(self._on_compute_mode_probe_done)
        self.mathcraft_pkg_probe_done.connect(self._set_mathcraft_pkg_ready)
        self._schedule_compute_mode_probe(force=True)
        self.btn_update.clicked.connect(lambda: check_update_dialog(self))
        self.btn_terminal.clicked.connect(lambda: self._open_terminal())
        self.terminal_env_combo.currentIndexChanged.connect(self._on_terminal_env_changed)
        self.btn_deps_wizard.clicked.connect(self._open_deps_wizard)
        self.btn_open_mathcraft_cache.clicked.connect(self._open_mathcraft_cache_dir)
        self.startup_console_checkbox.stateChanged.connect(self._on_startup_console_changed)
        self.theme_mode_combo.currentIndexChanged.connect(self._on_theme_mode_changed)
        # Render-engine related signals.
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
        self.external_prompt_combo.currentIndexChanged.connect(self._on_external_config_changed)
        self.external_base_url_input.textChanged.connect(self._on_external_config_changed)
        self.external_model_name_input.textChanged.connect(self._on_external_config_changed)
        self.external_api_key_input.textChanged.connect(self._on_external_config_changed)
        self.external_mineru_endpoint_input.textChanged.connect(self._on_external_config_changed)
        self.external_mineru_test_endpoint_input.textChanged.connect(self._on_external_config_changed)
        self.external_timeout_input.textChanged.connect(self._on_external_config_changed)
        self.external_custom_prompt_input.textChanged.connect(self._on_external_config_changed)
        # Initialize selection state.
        self._init_model_combo()
        self._update_model_desc()
        self._init_theme_mode_combo()
        self._init_render_engine()
        self._load_latex_settings()
        # Warm probe caches in the background to reduce first-click stalls for terminal/GPU install actions.
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
                "text": "#e7ebf0",
                "muted": "#b6beca",
                "compute_gpu": "#7bd88f",
                "compute_cpu": "#ffb35c",
                "compute_unknown": "#9ea7b3",
            }
        return {
            "text": "#222222",
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

    def _style_native_checkbox(self, checkbox: QCheckBox, text_color: str, disabled_color: str) -> None:
        pal = checkbox.palette()
        for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
            pal.setColor(group, QPalette.ColorRole.WindowText, QColor(text_color))
            pal.setColor(group, QPalette.ColorRole.ButtonText, QColor(text_color))
            pal.setColor(group, QPalette.ColorRole.Text, QColor(text_color))
        pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(disabled_color))
        pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(disabled_color))
        pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(disabled_color))
        checkbox.setPalette(pal)
        checkbox.setStyleSheet("")

    def apply_theme_styles(self, force: bool = False):
        dark = self._is_dark_mode()
        if not force and self._theme_is_dark_cached is dark:
            return
        self._theme_is_dark_cached = dark
        t = self._theme_tokens()
        if hasattr(self, "lbl_model_desc") and self.lbl_model_desc is not None:
            self.lbl_model_desc.setStyleSheet(f"color: {t['muted']}; font-size: 11px; padding: 4px;")
        if hasattr(self, "mathcraft_env_hint") and self.mathcraft_env_hint is not None:
            self.mathcraft_env_hint.setStyleSheet(f"color: {t['muted']}; font-size: 10px; padding: 2px;")
        if hasattr(self, "lbl_latex_desc") and self.lbl_latex_desc is not None:
            self.lbl_latex_desc.setStyleSheet(f"color: {t['muted']}; font-size: 10px; padding: 4px;")
        if hasattr(self, "lbl_compute_mode") and self.lbl_compute_mode is not None:
            self.lbl_compute_mode.setStyleSheet(
                f"color: {self._compute_label_color()}; font-size: 11px; padding: 4px;"
            )
        if hasattr(self, "startup_console_checkbox") and self.startup_console_checkbox is not None:
            self._style_native_checkbox(self.startup_console_checkbox, t["text"], t["muted"])

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
            # MathCraft v1 uses ONNX Runtime providers; keep this probe lightweight.
            try:
                self._schedule_compute_mode_probe(force=True)
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

    def _on_startup_console_changed(self, _state: int):
        # PyQt6 CheckState is not safely cast with int(); reading the widget state directly is safest.
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
        roots = _mathcraft_code_roots()
        code = (
            "import importlib.util, sys; "
            f"[sys.path.insert(0, p) for p in reversed({roots!r}) if p not in sys.path]; "
            f"sys.exit(0 if importlib.util.find_spec({module!r}) else 1)"
        )
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
    def _schedule_mathcraft_pkg_probe(self):
        pyexe = self.mathcraft_pyexe_input.text().strip()
        if not pyexe or not os.path.exists(pyexe):
            self._mathcraft_pkg_ready = False
            self._update_mathcraft_visibility()
            return
        def worker():
            ok = self._probe_module_installed(pyexe, "mathcraft_ocr")
            try:
                self.mathcraft_pkg_probe_done.emit(bool(ok))
            except Exception:
                pass
        import threading
        threading.Thread(target=worker, daemon=True).start()
    def _set_mathcraft_pkg_ready(self, ready: bool):
        self._mathcraft_pkg_ready = bool(ready)
        self._update_mathcraft_visibility()

    def _infer_compute_mode_from_env(self, pyexe: str) -> dict:
        try:
            env_root = self._python_env_root(pyexe)
            site = env_root / "Lib" / "site-packages"
            if not site.exists():
                return {}
            names = {d.name.lower() for d in site.iterdir()}
            has_ort = any(name.startswith("onnxruntime-") for name in names) or (site / "onnxruntime").exists()
            if not has_ort:
                return {}
            has_gpu_runtime = any(name.startswith("onnxruntime_gpu-") or name.startswith("onnxruntime-gpu-") for name in names)
            info = {
                "present": True,
                "providers": [],
                "gpu_name": "",
                "cpu_name": "",
                "gpu_available": False,
            }
            if has_gpu_runtime:
                info["providers"] = ["CUDAExecutionProvider"]
                info["gpu_available"] = True
            else:
                info["providers"] = ["CPUExecutionProvider"]
            return info
        except Exception:
            return {}

    def _probe_compute_mode_info(self, pyexe: str) -> dict:
        if not pyexe or not os.path.exists(pyexe):
            return {"present": False, "error": "python.exe not found"}
        code = (
            "import json\n"
            "out={'present': False, 'providers': [], 'gpu_available': False, 'gpu_name': '', 'cpu_name': ''}\n"
            "try:\n"
            " import onnxruntime as ort\n"
            " providers = list(ort.get_available_providers() or [])\n"
            " out['present'] = True\n"
            " out['providers'] = providers\n"
            " out['gpu_available'] = any(p in providers for p in ('CUDAExecutionProvider', 'TensorrtExecutionProvider', 'DmlExecutionProvider'))\n"
            "except Exception as e:\n"
            " out['error'] = f'{e.__class__.__name__}: {e}'\n"
            "print(json.dumps(out, ensure_ascii=False))\n"
        )
        try:
            res = subprocess.run(
                [pyexe, "-c", code],
                capture_output=True,
                text=True,
                timeout=6,
                creationflags=_subprocess_creationflags(),
            )
            raw = (res.stdout or "").strip()
            if raw:
                try:
                    info = json.loads(raw.splitlines()[-1])
                    if isinstance(info, dict):
                        gpu_name, cpu_name = self._probe_local_device_names()
                        if gpu_name and not info.get("gpu_name"):
                            info["gpu_name"] = gpu_name
                        if cpu_name and not info.get("cpu_name"):
                            info["cpu_name"] = cpu_name
                        return info
                except Exception:
                    pass
            env_info = self._infer_compute_mode_from_env(pyexe)
            if env_info:
                gpu_name, cpu_name = self._probe_local_device_names()
                if gpu_name and not env_info.get("gpu_name"):
                    env_info["gpu_name"] = gpu_name
                if cpu_name and not env_info.get("cpu_name"):
                    env_info["cpu_name"] = cpu_name
                return env_info
            return {"present": False, "error": (res.stderr or raw or "probe failed").strip()}
        except Exception as e:
            env_info = self._infer_compute_mode_from_env(pyexe)
            if env_info:
                gpu_name, cpu_name = self._probe_local_device_names()
                if gpu_name and not env_info.get("gpu_name"):
                    env_info["gpu_name"] = gpu_name
                if cpu_name and not env_info.get("cpu_name"):
                    env_info["cpu_name"] = cpu_name
                return env_info
            return {"present": False, "error": str(e)}

    def _probe_local_device_names(self) -> tuple[str, str]:
        now = time.monotonic()
        cached = getattr(self, "_device_name_cache", {}) or {}
        ttl = 300.0
        if (now - float(cached.get("ts", 0.0) or 0.0)) <= ttl:
            return str(cached.get("gpu", "") or ""), str(cached.get("cpu", "") or "")

        def _run_ps(cmd: str) -> str:
            try:
                res = subprocess.run(
                    ["powershell", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    creationflags=_subprocess_creationflags(),
                )
                lines = [line.strip() for line in (res.stdout or "").splitlines() if line.strip()]
                return lines[0] if lines else ""
            except Exception:
                return ""

        gpu_name = _run_ps("(Get-WmiObject Win32_VideoController | Where-Object {$_.Name -and $_.Name -notmatch 'Microsoft Basic'} | Select-Object -First 1 -ExpandProperty Name)")
        if not gpu_name:
            gpu_name = _run_ps("(Get-CimInstance Win32_VideoController | Where-Object {$_.Name -and $_.Name -notmatch 'Microsoft Basic'} | Select-Object -First 1 -ExpandProperty Name)")
        if not gpu_name:
            try:
                res = subprocess.run(
                    ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    creationflags=_subprocess_creationflags(),
                )
                names = [line.strip() for line in (res.stdout or "").splitlines() if line.strip()]
                gpu_name = names[0] if names else ""
            except Exception:
                gpu_name = ""

        cpu_name = _run_ps("(Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty Name)")
        if not cpu_name:
            cpu_name = _run_ps("(Get-WmiObject Win32_Processor | Select-Object -First 1 -ExpandProperty Name)")

        self._device_name_cache = {"gpu": gpu_name, "cpu": cpu_name, "ts": now}
        return gpu_name, cpu_name

    def _refresh_env_status(self, env_key: str):
        if env_key != "mathcraft":
            return
        self._schedule_compute_mode_probe(force=True)
        self._schedule_mathcraft_pkg_probe()

    def _onnxruntime_cpu_spec(self) -> str:
        return onnxruntime_cpu_spec(self._current_mathcraft_pyexe())

    def _onnxruntime_gpu_command(self) -> str:
        return onnxruntime_gpu_policy(self._current_mathcraft_pyexe()).pip_command() + " --no-deps"

    def _current_mathcraft_pyexe(self) -> str:
        try:
            return self.mathcraft_pyexe_input.text().strip()
        except Exception:
            return ""

    def _init_model_combo(self):
        # Initialize the model combo-box selection.
        current = "mathcraft"
        if self.parent() and hasattr(self.parent(), "desired_model"):
            current = self.parent().desired_model
        elif self.parent() and hasattr(self.parent(), "cfg"):
            current = self.parent().cfg.get("desired_model", current)
        if not current and self.parent() and hasattr(self.parent(), "current_model"):
            current = self.parent().current_model
        if current and str(current).startswith("mathcraft"):
            current_key = "mathcraft"
        else:
            current_key = current
        for i, (key, _) in enumerate(self._model_options):
            if key == current_key:
                self.model_combo.setCurrentIndex(i)
                break
        self._init_mathcraft_pyexe()
        self._schedule_mathcraft_pkg_probe()
        self._init_mathcraft_mode()
        self._init_external_model_config()
        self._update_mathcraft_visibility()
    def _on_model_combo_changed(self, index: int):
        # Model combo-box selection changed.
        if getattr(self, "_model_selection_syncing", False):
            return
        if index < 0 or index >= len(self._model_options):
            return
        key, _ = self._model_options[index]
        if key == "external_model":
            self.select_model("external_model")
        elif self._is_mathcraft_ready():
            mode_key = self._get_mathcraft_mode_key()
            self.select_model(self._mathcraft_mode_to_model(mode_key))
        else:
            # Trigger loading or hints while keeping the UI selection on mathcraft.
            self.select_model("mathcraft")
        self._update_model_desc()
        self._update_mathcraft_visibility()
    def _init_mathcraft_pyexe(self):
        pyexe = self._resolve_dynamic_main_pyexe()
        self.mathcraft_pyexe_input.setText(pyexe)
        cfg = self._settings_cfg()
        if cfg:
            cfg.set("mathcraft_pyexe", pyexe)
    def _init_mathcraft_mode(self):
        mode = "formula"
        if self.parent() and hasattr(self.parent(), "cfg"):
            mode = self.parent().cfg.get("mathcraft_mode", "formula")
        if mode not in {"formula", "mixed", "text"}:
            mode = "formula"
        for i in range(self.mathcraft_mode_combo.count()):
            if self.mathcraft_mode_combo.itemData(i) == mode:
                prev = self.mathcraft_mode_combo.blockSignals(True)
                self.mathcraft_mode_combo.setCurrentIndex(i)
                self.mathcraft_mode_combo.blockSignals(prev)
                break

    def _mathcraft_mode_to_model(self, mode_key: str) -> str:
        mapping = {
            "formula": "mathcraft",
            "mixed": "mathcraft_mixed",
            "text": "mathcraft_text",
        }
        return mapping.get(mode_key, "mathcraft")
    def _get_mathcraft_mode_key(self) -> str:
        idx = self.mathcraft_mode_combo.currentIndex()
        if idx >= 0:
            key = self.mathcraft_mode_combo.itemData(idx)
            if key:
                return key
        return "formula"

    def _settings_cfg(self):
        if self.parent() and hasattr(self.parent(), "cfg"):
            return self.parent().cfg
        return None
    @staticmethod
    def _normalize_install_base_dir(selected_dir: Path) -> Path:
        path = Path(selected_dir).expanduser()
        try:
            path = path.resolve()
        except Exception:
            path = path.absolute()
        if not path.exists() or not path.is_dir():
            return path
        leaf = path.name.lower()
        if not (leaf.startswith("python") or leaf in {"venv", ".venv", "scripts", "python_full"}):
            return path
        existing_py = SettingsWindow._find_install_base_python(path)
        if existing_py is not None:
            return path
        return path.parent if path.parent != path else path
    @staticmethod
    def _find_install_base_python(base_dir: Path) -> Path | None:
        base_dir = Path(base_dir)
        candidates = [
            base_dir / "python.exe",
            base_dir / "Scripts" / "python.exe",
            base_dir / "python311" / "python.exe",
            base_dir / "python311" / "Scripts" / "python.exe",
            base_dir / "Python311" / "python.exe",
            base_dir / "Python311" / "Scripts" / "python.exe",
            base_dir / "venv" / "Scripts" / "python.exe",
            base_dir / ".venv" / "Scripts" / "python.exe",
            base_dir / "python_full" / "python.exe",
        ]
        try:
            for child in sorted(base_dir.glob("python*")):
                if child.is_dir():
                    candidates.append(child / "python.exe")
                    candidates.append(child / "Scripts" / "python.exe")
        except Exception:
            pass
        for candidate in candidates:
            try:
                if candidate.exists() and candidate.is_file():
                    return candidate
            except Exception:
                continue
        return None
    @staticmethod
    def _python_env_root(pyexe: str | Path) -> Path:
        p = Path(pyexe)
        return p.parent.parent if p.parent.name.lower() == "scripts" else p.parent
    def _current_install_base_dir(self) -> Path | None:
        cfg = self._settings_cfg()
        raw = ""
        try:
            if cfg:
                raw = cfg.get("install_base_dir", "") or ""
        except Exception:
            raw = ""
        if not raw:
            raw = os.environ.get("LATEXSNIPPER_INSTALL_BASE_DIR", "") or ""
        raw = str(raw).strip()
        if not raw:
            return None
        try:
            return self._normalize_install_base_dir(Path(raw))
        except Exception:
            return None
    def _resolve_dynamic_main_pyexe(self) -> str:
        base_dir = self._current_install_base_dir()
        if base_dir is not None:
            candidate = self._find_install_base_python(base_dir)
            if candidate is not None:
                return str(candidate)
            return ""
        env_pyexe = (os.environ.get("LATEXSNIPPER_PYEXE", "") or "").strip()
        if env_pyexe and os.path.exists(env_pyexe):
            if getattr(sys, "frozen", False):
                try:
                    if os.path.normcase(os.path.abspath(env_pyexe)) == os.path.normcase(os.path.abspath(sys.executable)):
                        return ""
                except Exception:
                    pass
            return env_pyexe
        return ""
    def _is_mathcraft_selected(self) -> bool:
        idx = self.model_combo.currentIndex()
        if idx >= 0 and idx < len(self._model_options):
            key, _ = self._model_options[idx]
            return key == "mathcraft"
        return False
    def _is_external_model_selected(self) -> bool:
        idx = self.model_combo.currentIndex()
        if idx >= 0 and idx < len(self._model_options):
            key, _ = self._model_options[idx]
            return key == "external_model"
        return False
    def _is_mathcraft_ready(self) -> bool:
        # only mark ready after MathCraft package is available
        if getattr(self, "_mathcraft_pkg_ready", False):
            return True
        return False
    def _on_mathcraft_mode_changed(self, index: int):
        if index < 0:
            return
        mode_key = self.mathcraft_mode_combo.itemData(index)
        if self.parent() and hasattr(self.parent(), "cfg"):
            self.parent().cfg.set("mathcraft_mode", mode_key)
        if not self._is_mathcraft_selected():
            return
        if self._is_mathcraft_ready():
            self.select_model(self._mathcraft_mode_to_model(mode_key))

    def _update_mathcraft_visibility(self):
        key = None
        idx = self.model_combo.currentIndex()
        if idx >= 0 and idx < len(self._model_options):
            key, _ = self._model_options[idx]
        visible = (key == "mathcraft")
        external_visible = (key == "external_model")
        ready = self._is_mathcraft_ready()
        pyexe = self.mathcraft_pyexe_input.text().strip()
        pyexe_exists = bool(pyexe and Path(pyexe).exists())
        try:
            self.mathcraft_env_widget.setVisible(visible)
            self.mathcraft_env_hint.setVisible(visible)
            if self.mathcraft_dl_widget is not None:
                self.mathcraft_dl_widget.setVisible(visible)
            # Keep recognition type visible so users can preselect it.
            self.mathcraft_mode_widget.setVisible(visible)
            self.external_model_widget.setVisible(external_visible)
            if visible:
                if not pyexe_exists:
                    self.mathcraft_env_hint.setText("⚠️ 主依赖环境未就绪，请先运行依赖向导。")
                elif not ready:
                    self.mathcraft_env_hint.setText("⚠️ MathCraft 未部署：请检查程序文件或依赖环境。")
                else:
                    self.mathcraft_env_hint.setText("💡 MathCraft 已就绪，可选择识别类型。")
            if external_visible:
                self._update_external_model_status()
        except Exception:
            pass
    def _init_render_engine(self):
        """Initialize render-engine selection."""
        try:
            from backend.latex_renderer import _latex_settings, LaTeXRenderer
            if _latex_settings:
                mode = _latex_settings.get_render_mode()
                self.render_engine_combo.currentIndexChanged.disconnect(self._on_render_engine_changed)
                # Find the matching index from _render_modes.
                if mode in self._render_modes:
                    index = self._render_modes.index(mode)
                    self.render_engine_combo.setCurrentIndex(index)
                else:
                    # Default to auto detection.
                    self.render_engine_combo.setCurrentIndex(0)
                self.render_engine_combo.currentIndexChanged.connect(self._on_render_engine_changed)
                current_index = self.render_engine_combo.currentIndex()
                if current_index >= 0 and current_index < len(self._render_modes):
                    engine = self._render_modes[current_index]
                    is_latex = engine.startswith("latex_")
                    self.latex_options_widget.setVisible(is_latex)
                    # Try auto detection in LaTeX mode.
                    if is_latex and not _latex_settings.get_latex_path():
                        renderer = LaTeXRenderer()
                        if renderer.is_available():
                            self.latex_path_input.setText(renderer.latex_cmd)
                            _latex_settings.set_latex_path(renderer.latex_cmd)
                            _latex_settings.save()
        except Exception as e:
            print(f"[WARN] 初始化渲染引擎失败: {e}")
    def _on_render_engine_changed(self, index: int):
        """Handle render-engine changes immediately without heavy validation on the UI thread."""
        if index < 0:
            return
        # Read the engine data from _render_modes.
        if index < 0 or index >= len(self._render_modes):
            print(f"[WARN] 渲染引擎索引无效: {index}")
            return
        engine = self._render_modes[index]
        # Show or hide LaTeX options.
        is_latex = engine.startswith("latex_")
        self.latex_options_widget.setVisible(is_latex)
        if is_latex:
            self._sync_latex_path_for_engine(engine)
            latex_path = self.latex_path_input.text().strip()
            if not latex_path:
                self._show_notification("warning", "LaTeX 路径未配置", "已切换引擎。请点击“自动检测”或手动选择路径，再点“验证路径”。")

        # Save engine changes immediately; expensive validation is triggered by the path validation button.
        self._save_render_mode(engine)
    def _load_latex_settings(self):
        """Load LaTeX settings."""
        try:
            from backend.latex_renderer import _latex_settings
            if _latex_settings:
                latex_path = _latex_settings.get_latex_path()
                if latex_path:
                    self.latex_path_input.setText(latex_path)
        except Exception as e:
            print(f"[WARN] 加载 LaTeX 设置失败: {e}")
    def _on_latex_path_changed(self):
        """Handle LaTeX path changes by clearing validation state."""
        if getattr(self, "_latex_test_in_progress", False):
            return
        self.btn_test_latex.setText("验证路径")
        self.btn_test_latex.setEnabled(True)
    def _browse_latex_path(self):
        """Browse for a LaTeX executable path."""
        file_path, _ = _select_open_file_with_icon(
            self,
            "选择 pdflatex 或 xelatex 可执行文件",
            "",
            "可执行文件 (pdflatex.exe xelatex.exe);;所有文件 (*.*)"
        )
        if file_path:
            self.latex_path_input.setText(file_path)
            self._save_latex_settings()
    def _detect_latex(self):
        """Detect LaTeX asynchronously, checking both pdflatex and xelatex."""
        if getattr(self, "_latex_detect_in_progress", False):
            return

        self._latex_detect_in_progress = True
        self.btn_detect_latex.setText("检测中...")
        self.btn_detect_latex.setEnabled(False)

        # Use the current render-engine selection as the detection preference; infer from the current path outside LaTeX mode.
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

            # If PATH misses, infer the sibling compiler from the current path directory.
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
        """Save LaTeX settings."""
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
        """Test the LaTeX path asynchronously to avoid blocking the UI thread."""
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
            # Save directly if the path was unchanged during validation; otherwise keep the success state visible.
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
        """Show a floating notification."""
        try:
            from qfluentwidgets import InfoBar, InfoBarPosition
            # Call the matching method for the requested level.
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
        """Save the render-engine selection."""
        try:
            from backend.latex_renderer import _latex_settings
            if _latex_settings:
                _latex_settings.set_render_mode(engine)
                print(f"[Render] 已切换渲染引擎: {engine}")
                # Show success through a floating InfoBar instead of MessageBox.
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
        # Update model description.
        index = self.model_combo.currentIndex()
        if index < 0:
            return
        key, _ = self._model_options[index]
        descriptions = {
            "mathcraft": "内置 MathCraft OCR，支持公式、混合、文字与 PDF 文档识别。",
            "external_model": "连接本地多模态 OCR / VLM 接口，适合接入 Qwen、GLM-OCR、PaddleOCR-VL 等本地服务。",
        }
        desc = descriptions.get(key, "")
        if key == "mathcraft":
            desc += "\n提示：MathCraft 依赖由主环境统一管理，权重位于 MathCraft 标准缓存目录。"
        elif key == "external_model":
            desc += "\n提示：支持本地和部分线上接口。必填：协议、Base URL、模型名；选填：API Key、提示词。"
        self.lbl_model_desc.setText(desc)
    def _open_terminal(self, env_key: str | None = None):
        if isinstance(env_key, bool):
            env_key = None
        import subprocess
        import os
        if env_key is None:
            env_key = self._get_terminal_env_key()
        # Always open only the main environment terminal.
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
        
        pyexe = self._resolve_dynamic_main_pyexe()
        print(f"[DEBUG] Terminal pyexe initial: {pyexe}")
        if not pyexe or not os.path.exists(pyexe):
            msg = MessageBox(
                "环境未就绪",
                "当前依赖目录尚未初始化 Python 环境。\n\n请先在【依赖管理向导】中初始化依赖环境，再打开环境终端。",
                self,
            )
            _apply_app_window_icon(msg)
            msg.yesButton.setText("OK")
            msg.cancelButton.hide()
            msg.exec()
            return
        env_root = self._python_env_root(pyexe)
        pyexe_dir = str(env_root)
        scripts_dir = os.path.join(pyexe_dir, "Scripts")
        base_dir = self._current_install_base_dir()
        venv_dir = str(base_dir or env_root)
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
        _apply_app_window_icon(msg)
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
        env_desc = "主环境（程序 / MathCraft / 核心依赖）"
        gpu_onnx_cmd = self._onnxruntime_gpu_command()
        cpu_onnx_cmd = f'pip install "{self._onnxruntime_cpu_spec()}"'
        help_lines = [
            "echo.",
            "echo ================================================================================",
            f"echo                        LaTeXSnipper Terminal - {env_name}",
            "echo ================================================================================",
            "echo.",
            f"echo [*] Env: {env_desc}",
            f"echo [*] Python env root: {pyexe_dir}",
            "echo [*] python/pip are bound to this env for this terminal session",
            "echo.",
            "echo [Model Policy]",
            "echo   - built-in OCR uses MathCraft model cache",
            "echo   - external_model uses independently deployed local/online services",
            "echo   - terminal commands target the current main dependency env",
            "echo   - MathCraft uses ONNX Runtime providers for the internal OCR path",
            "echo   - MATHCRAFT_CPU/MATHCRAFT_GPU select CPU/GPU ONNX Runtime backends",
            "echo.",
            "echo [Version Fix]",
            "echo   pip install \"protobuf>=3.20,<5\"",
            "echo.",
            "echo [ONNX Runtime]",
            f"echo   {gpu_onnx_cmd}",
            f"echo   {cpu_onnx_cmd}",
            "echo.",
            "echo [Model]",
            "echo   # Step-by-step install (stable order)",
            "echo   pip install -U pip setuptools wheel --default-timeout 180 --retries 15 --prefer-binary --extra-index-url https://pypi.org/simple",
            "echo   pip install -U \"transformers==4.55.4\" \"tokenizers==0.21.4\" --default-timeout 180 --retries 15 --prefer-binary --extra-index-url https://pypi.org/simple",
            "echo   # MathCraft is shipped with LaTeXSnipper source/package; verify it from the project root.",
            "echo   pip install -U \"protobuf>=3.20,<5\" \"pymupdf~=1.27.2.2\" --default-timeout 180 --retries 15 --prefer-binary --extra-index-url https://pypi.org/simple",
            "echo.",
            "echo [MathCraft CPU/ONNX Check]",
            "echo   python -c \"import sys; sys.path.insert(0, r'%CD%'); from mathcraft_ocr.cli import main; raise SystemExit(main(['doctor','--provider','cpu']))\"",
            "echo.",
        ]
        help_lines += [
            "echo [Diagnostics]",
            "echo   pip list",
            "echo   pip check",
            "echo   python -c \"import onnxruntime as ort; print(ort.__version__, ort.get_available_providers())\"",
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
        python_bind_lines = (
            f'set "LATEXSNIPPER_PYEXE={pyexe}"\n'
            f'doskey python="{pyexe}" $*\n'
            f'doskey py="{pyexe}" $*\n'
            f'doskey pip="{pyexe}" -m pip $*\n'
            "echo [*] python macro : %LATEXSNIPPER_PYEXE%\n"
            "echo [*] pip macro    : %LATEXSNIPPER_PYEXE% -m pip\n"
            "echo.\n"
        )
        try:
            if as_admin:
                import tempfile
                batch_content = ("@echo off\n"
                    + f'cd /d "{venv_dir}"\n'
                    + f'set "PATH={pyexe_dir};{scripts_dir};%PATH%"\n'
                    + python_bind_lines
                    + help_text
                )
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
                batch_content_normal = ("@echo off\n"
                    + f'cd /d "{venv_dir}"\n'
                    + f'set "PATH={pyexe_dir};{scripts_dir};%PATH%"\n'
                    + python_bind_lines
                    + help_text
                )
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

    def _resolve_mathcraft_cache_dir(self) -> str:
        appdata = (os.environ.get("APPDATA", "") or "").strip()
        if appdata:
            return os.path.normpath(os.path.join(appdata, "MathCraft", "models"))
        return os.path.normpath(os.path.expanduser("~/.MathCraft/models"))

    def _open_mathcraft_cache_dir(self):
        path = self._resolve_mathcraft_cache_dir()
        try:
            os.makedirs(path, exist_ok=True)
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
            self._show_info("已打开", f"MathCraft 缓存目录: {path}", "success")
        except Exception as e:
            self._show_info("打开失败", f"无法打开缓存目录: {e}", "error")

    def _open_deps_wizard(self):
        """Open the dependency management wizard."""
        msg = MessageBox(
            "打开依赖向导",
            "依赖管理向导将以重启后的干净进程打开。\n\n是否立即重启并打开依赖向导？\n• ESC取消操作",
            self
        )
        _apply_app_window_icon(msg)
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
        """Restart the app and open the dependency wizard."""
        import sys
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QCoreApplication
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
            # Release heavy resources and the instance lock first to reduce the chance that the new process cannot acquire the lock.
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
            spawn_flags = int(_subprocess_creationflags()) if getattr(sys, "frozen", False) else 0
            subprocess.Popen(
                [str(x) for x in spawn_argv],
                env=env,
                creationflags=spawn_flags,
            )
            # Close the current program.
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
        """Show a Fluent floating notification."""
        from qfluentwidgets import InfoBar, InfoBarPosition
        # Anchor to the settings window to avoid covering the main window.
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
        return f"{provider}|{base_url}|{model_name}|{mineru_endpoint}"

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
        self._set_lineedit_value(self.external_mineru_endpoint_input, str(preset.get("mineru_endpoint") or "/file_parse"))
        self._set_lineedit_value(self.external_mineru_test_endpoint_input, str(preset.get("mineru_test_endpoint") or "/health"))
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
                    "原生解析"
                )
            else:
                status = f"状态：{state_text}。协议 {provider_label}，模型 {model_name}"
        if test_message:
            status = f"{status}\n最近一次测试：{test_message}"
        elif saved_message and tested_sig == current_sig:
            status = f"{status}\n最近一次测试：{saved_message}"
        self.external_status.setText(status)
    def select_model(self, model_name: str):
        # Only emit the signal; the connected on_model_changed handler processes it.
        self.model_changed.emit(model_name)
        self._update_compute_mode_label()

    def _set_compute_mode_text(self, text: str, state: str) -> None:
        self.lbl_compute_mode.setText(text)
        self._compute_mode_state = state
        self.apply_theme_styles(force=True)

    def _set_compute_mode_detecting(self, info: dict, pyexe: str) -> None:
        if not pyexe or not os.path.exists(pyexe):
            self._set_compute_mode_text("⚪ 计算模式检测中...", "unknown")
            return
        providers = [str(p or "").strip() for p in (info.get("providers") or [])]
        gpu_available = any(
            p in ("CUDAExecutionProvider", "TensorrtExecutionProvider", "DmlExecutionProvider")
            for p in providers
        )
        if gpu_available:
            self._set_compute_mode_text("🟢 GPU 模式（检测中...）", "gpu")
        elif info.get("present"):
            self._set_compute_mode_text("🟡 CPU 模式（检测中...）", "cpu")
        else:
            self._set_compute_mode_text("⚪ 计算模式检测中...", "unknown")

    def _apply_compute_mode_from_info(self, info: dict, pyexe: str) -> bool:
        if not pyexe or not os.path.exists(pyexe):
            self._set_compute_mode_text("⚪ 计算模式未知", "unknown")
            return True
        if not isinstance(info, dict) or not info:
            return False
        if not info.get("present"):
            self._set_compute_mode_text("⚪ 计算模式未知", "unknown")
            return True
        providers = [str(p or "").strip() for p in (info.get("providers") or [])]
        gpu_available = any(
            p in ("CUDAExecutionProvider", "TensorrtExecutionProvider", "DmlExecutionProvider")
            for p in providers
        )
        gpu_name = str(info.get("gpu_name") or "").strip()
        cpu_name = str(info.get("cpu_name") or "").strip()
        if gpu_available:
            if gpu_name:
                self._set_compute_mode_text(f"🟢 GPU 可用: {gpu_name}", "gpu")
            else:
                self._set_compute_mode_text("🟢 GPU 模式", "gpu")
            return True
        if cpu_name:
            self._set_compute_mode_text(f"🟡 CPU 模式: {cpu_name}", "cpu")
        else:
            self._set_compute_mode_text("🟡 CPU 模式", "cpu")
        return True

    def _on_compute_mode_probe_done(self, info: object, pyexe: str) -> None:
        self._compute_mode_probe_running = False
        self._compute_mode_probe_py = str(pyexe or "")
        self._compute_mode_probe_ts = time.monotonic()
        self._compute_mode_probe_info = dict(info) if isinstance(info, dict) else {}
        self._apply_compute_mode_from_info(self._compute_mode_probe_info or {}, self._compute_mode_probe_py)

    def _schedule_compute_mode_probe(self, force: bool = False) -> None:
        pyexe = self._resolve_dynamic_main_pyexe()
        if not pyexe or not os.path.exists(pyexe):
            self._set_compute_mode_text("⚪ 计算模式未知", "unknown")
            return

        now = time.monotonic()
        ttl = float(getattr(self, "_probe_cache_ttl_sec", 45.0) or 45.0)
        cached_info = getattr(self, "_compute_mode_probe_info", None)
        cached_py = str(getattr(self, "_compute_mode_probe_py", "") or "")
        cached_ts = float(getattr(self, "_compute_mode_probe_ts", 0.0) or 0.0)
        if (not force) and cached_py == pyexe and isinstance(cached_info, dict) and (now - cached_ts) <= ttl:
            self._apply_compute_mode_from_info(cached_info, pyexe)
            return

        inferred = self._infer_compute_mode_from_env(pyexe)
        if self._apply_compute_mode_from_info(inferred, pyexe):
            if isinstance(inferred, dict) and inferred.get("present"):
                self._compute_mode_probe_py = pyexe
                self._compute_mode_probe_ts = now
                self._compute_mode_probe_info = dict(inferred)
        else:
            self._set_compute_mode_text("⚪ 计算模式检测中...", "unknown")

        if self._compute_mode_probe_running and not force:
            return

        if isinstance(inferred, dict) and inferred.get("present"):
            self._set_compute_mode_detecting(inferred, pyexe)
        else:
            self._set_compute_mode_text("⚪ 计算模式检测中...", "unknown")

        self._compute_mode_probe_running = True

        def worker():
            info = self._probe_compute_mode_info(pyexe)
            try:
                self.compute_mode_probe_done.emit(info, pyexe)
            except Exception:
                pass

        import threading
        threading.Thread(target=worker, daemon=True).start()

    def _update_compute_mode_label(self):
        """Update the compute-mode status label, preferring cache and probing in the background."""
        self._schedule_compute_mode_probe()
    def update_model_selection(self):
        # sync model combo selection state
        if getattr(self, "_model_selection_syncing", False):
            return
        current = "mathcraft"
        try:
            if self.parent() and hasattr(self.parent(), "desired_model"):
                current = str(self.parent().desired_model or "mathcraft")
            elif self.parent() and hasattr(self.parent(), "cfg"):
                current = str(self.parent().cfg.get("desired_model", current) or current)
        except Exception:
            current = "mathcraft"
        target = "external_model" if current == "external_model" else "mathcraft"
        self._model_selection_syncing = True
        try:
            for i, (key, _) in enumerate(self._model_options):
                if key == target:
                    self.model_combo.blockSignals(True)
                    self.model_combo.setCurrentIndex(i)
                    self.model_combo.blockSignals(False)
                    break
            self._init_mathcraft_mode()
            self._init_external_model_config()
            self._update_model_desc()
            self._update_mathcraft_visibility()
        finally:
            self._model_selection_syncing = False

# ---------------- Main Window ----------------
