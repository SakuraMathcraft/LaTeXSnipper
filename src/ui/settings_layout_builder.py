from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QLineEdit, QScrollArea, QVBoxLayout, QWidget
from qfluentwidgets import ComboBox, FluentIcon, PrimaryPushButton, PushButton

from backend.external_model import PRESET_ITEMS
from runtime.distribution import is_store_distribution
from update.update_dialog import check_update_dialog


class SettingsLayoutMixin:

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
            "自动检测（推荐）",
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
        self.startup_console_checkbox = QCheckBox("启动时显示日志窗口")
        startup_console_pref = False
        try:
            if self.parent() and hasattr(self.parent(), "cfg"):
                startup_console_pref = self.parent().cfg.get("show_startup_console", False)
        except Exception:
            startup_console_pref = False
        self.startup_console_checkbox.setChecked(self._to_bool(startup_console_pref))
        self.startup_console_checkbox.setToolTip("开启后将显示初始化与运行日志窗口")
        lay.addWidget(self.startup_console_checkbox)
        # Separator.
        lay.addSpacing(8)
        # Advanced action: open terminal; use carefully.
        lay.addWidget(QLabel("高级设置:"))
        terminal_row = QWidget()
        terminal_layout = QHBoxLayout(terminal_row)
        terminal_layout.setContentsMargins(0, 0, 0, 0)
        terminal_layout.setSpacing(6)
        self.terminal_env_button = PushButton(FluentIcon.APPLICATION, "主环境")
        self.terminal_env_button.setFixedHeight(36)
        self.terminal_env_button.setToolTip("当前唯一可管理的依赖环境")
        terminal_layout.addWidget(self.terminal_env_button, 1)
        self.btn_terminal = PushButton(FluentIcon.COMMAND_PROMPT, "打开环境终端")
        self.btn_terminal.setFixedHeight(36)
        self.btn_terminal.setToolTip("打开所选环境的终端，可手动安装/修复依赖。\n⚠️ 请谨慎操作，错误的命令可能损坏环境！")
        terminal_layout.addWidget(self.btn_terminal, 1)
        lay.addWidget(terminal_row)
        # Dependency management wizard and cache directory.
        deps_row = QWidget()
        deps_row_layout = QHBoxLayout(deps_row)
        deps_row_layout.setContentsMargins(0, 0, 0, 0)
        deps_row_layout.setSpacing(6)
        self.btn_deps_wizard = PushButton(FluentIcon.DEVELOPER_TOOLS, "依赖管理向导")
        self.btn_deps_wizard.setFixedHeight(36)
        self.btn_deps_wizard.setToolTip("打开依赖管理向导，可安装/修复依赖。\n从设置页进入会执行真实依赖校验。")
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
