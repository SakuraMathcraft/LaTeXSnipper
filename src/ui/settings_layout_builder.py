import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import ComboBox, FluentIcon, PrimaryPushButton, PushButton

from backend.external_model import PRESET_ITEMS
from localization.manager import translate as tr
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
        self.setWindowTitle(tr("设置"))
        # Use a wider default size to avoid truncating InfoBar text.
        self.resize(500, 600)
        self.setMinimumWidth(500)
        self.setMinimumHeight(600)
        root = QVBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.content_widget = QWidget(self)
        lay = QVBoxLayout(self.content_widget)
        lay.setSpacing(8)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setWidget(self.content_widget)
        root.addWidget(self.scroll_area)
        # Cache slow probe results to avoid blocking the UI on repeated clicks.
        self._probe_cache_ttl_sec = 45.0
        self._compute_mode_probe_py = ""
        self._compute_mode_probe_ts = 0.0
        self._compute_mode_probe_info = None
        self._compute_mode_probe_running = False
        self._theme_mode_values = ["auto", "light", "dark"]
        self._ui_language_values = ["auto", "zh_CN", "en_US"]
        # Model selection area.
        lay.addWidget(QLabel(tr("选择识别模型:")))
        # Use a combo box for built-in and external model entries.
        self.model_combo = ComboBox()
        self.model_combo.setFixedHeight(36)
        # Add recognition model options.
        self._model_options = [
            ("mathcraft", tr("内置模型")),
            ("external_model", tr("外部模型")),
        ]
        for key, label in self._model_options:
            self.model_combo.addItem(label, userData=key)
        lay.addWidget(self.model_combo)
        # Model description.
        self.lbl_model_desc = QLabel()
        self.lbl_model_desc.setStyleSheet("color: #666; font-size: 11px; padding: 4px;")
        self.lbl_model_desc.setWordWrap(True)
        lay.addWidget(self.lbl_model_desc)
        # MathCraft recognition type.
        self.mathcraft_mode_widget = QWidget()
        mathcraft_mode_layout = QHBoxLayout(self.mathcraft_mode_widget)
        mathcraft_mode_layout.setContentsMargins(0, 0, 0, 0)
        mathcraft_mode_layout.setSpacing(6)
        mathcraft_mode_layout.addWidget(QLabel(tr("MathCraft 识别类型:")))
        self.mathcraft_mode_combo = ComboBox()
        self.mathcraft_mode_combo.setFixedHeight(30)
        self.mathcraft_mode_combo.addItem(tr("公式"), userData="formula")
        self.mathcraft_mode_combo.addItem(tr("混合"), userData="mixed")
        self.mathcraft_mode_combo.addItem(tr("纯文字"), userData="text")
        self.mathcraft_mode_combo.currentIndexChanged.connect(
            self._on_mathcraft_mode_changed
        )
        mathcraft_mode_layout.addWidget(self.mathcraft_mode_combo)
        lay.addWidget(self.mathcraft_mode_widget)
        self.external_model_widget = QWidget()
        external_layout = QVBoxLayout(self.external_model_widget)
        external_layout.setContentsMargins(0, 6, 0, 0)
        external_layout.setSpacing(6)
        preset_row = QHBoxLayout()
        preset_row.setContentsMargins(0, 0, 0, 0)
        preset_row.setSpacing(6)
        preset_row.addWidget(QLabel(tr("推荐预设:")))
        self.external_preset_combo = ComboBox()
        self.external_preset_combo.setFixedHeight(30)
        self.external_preset_combo.addItem(tr("不使用预设"), userData="")
        for key, label in PRESET_ITEMS:
            self.external_preset_combo.addItem(label, userData=key)
        preset_row.addWidget(self.external_preset_combo, 1)
        self.external_apply_preset_btn = PushButton(FluentIcon.ROTATE, tr("应用预设"))
        self.external_apply_preset_btn.setFixedHeight(30)
        preset_row.addWidget(self.external_apply_preset_btn)
        external_layout.addLayout(preset_row)
        protocol_row = QHBoxLayout()
        protocol_row.setContentsMargins(0, 0, 0, 0)
        protocol_row.setSpacing(6)
        protocol_row.addWidget(QLabel(tr("协议:")))
        self.external_provider_combo = ComboBox()
        self.external_provider_combo.setFixedHeight(30)
        self.external_provider_combo.addItem(
            "OpenAI-compatible", userData="openai_compatible"
        )
        self.external_provider_combo.addItem("Ollama", userData="ollama")
        self.external_provider_combo.addItem("MinerU Local", userData="mineru")
        protocol_row.addWidget(self.external_provider_combo, 1)
        external_layout.addLayout(protocol_row)
        self.external_base_url_input = QLineEdit()
        self.external_base_url_input.setPlaceholderText(
            tr(
                "必填：Base URL，例如本地 http://127.0.0.1:11434 或线上 https://api.example.com"
            )
        )
        self.external_base_url_input.setFixedHeight(32)
        external_layout.addWidget(self.external_base_url_input)
        self.external_model_name_input = QLineEdit()
        self.external_model_name_input.setPlaceholderText(
            tr("必填：模型名，例如 qwen2.5vl:7b；必须与服务中的真实名称一致")
        )
        self.external_model_name_input.setFixedHeight(32)
        external_layout.addWidget(self.external_model_name_input)
        self.external_api_key_input = QLineEdit()
        self.external_api_key_input.setPlaceholderText(
            tr("选填：API Key。本地加密保存，线上接口通常必填")
        )
        self.external_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.external_api_key_input.setFixedHeight(32)
        external_layout.addWidget(self.external_api_key_input)
        self.external_mineru_endpoint_input = QLineEdit()
        self.external_mineru_endpoint_input.setPlaceholderText(
            tr("MinerU Local 解析接口路径（例如 /file_parse）")
        )
        self.external_mineru_endpoint_input.setFixedHeight(32)
        external_layout.addWidget(self.external_mineru_endpoint_input)
        self.external_mineru_test_endpoint_input = QLineEdit()
        self.external_mineru_test_endpoint_input.setPlaceholderText(
            tr("MinerU Local 健康检查路径（例如 /health）")
        )
        self.external_mineru_test_endpoint_input.setFixedHeight(32)
        external_layout.addWidget(self.external_mineru_test_endpoint_input)
        output_row = QHBoxLayout()
        output_row.setContentsMargins(0, 0, 0, 0)
        output_row.setSpacing(6)
        self.external_prompt_label = QLabel(tr("提示词模板:"))
        output_row.addWidget(self.external_prompt_label)
        self.external_prompt_combo = ComboBox()
        self.external_prompt_combo.setFixedHeight(30)
        self.external_prompt_combo.addItem(tr("公式 OCR"), userData="ocr_formula_v1")
        self.external_prompt_combo.addItem("Markdown OCR", userData="ocr_markdown_v1")
        self.external_prompt_combo.addItem(tr("纯文本 OCR"), userData="ocr_text_v1")
        output_row.addWidget(self.external_prompt_combo, 1)
        output_row.addWidget(QLabel(tr("超时(秒):")))
        self.external_timeout_input = QLineEdit()
        self.external_timeout_input.setPlaceholderText("60")
        self.external_timeout_input.setFixedHeight(30)
        self.external_timeout_input.setMaximumWidth(90)
        output_row.addWidget(self.external_timeout_input)
        external_layout.addLayout(output_row)
        self.external_custom_prompt_input = QLineEdit()
        self.external_custom_prompt_input.setPlaceholderText(
            tr("自定义提示词（覆盖图片、截图、手写及 OpenAI/Ollama PDF 模板）")
        )
        self.external_custom_prompt_input.setFixedHeight(32)
        external_layout.addWidget(self.external_custom_prompt_input)
        external_btn_row = QHBoxLayout()
        external_btn_row.setContentsMargins(0, 0, 0, 0)
        external_btn_row.setSpacing(6)
        self.external_test_btn = PrimaryPushButton(
            FluentIcon.SPEED_HIGH, tr("测试连接")
        )
        self.external_test_btn.setFixedHeight(32)
        external_btn_row.addWidget(self.external_test_btn)
        self.external_help_btn = PushButton(FluentIcon.INFO, tr("查看说明"))
        self.external_help_btn.setFixedHeight(32)
        external_btn_row.addWidget(self.external_help_btn)
        external_layout.addLayout(external_btn_row)
        lay.addWidget(self.external_model_widget)
        self.lbl_compute_mode = QLabel()
        self.lbl_compute_mode.setStyleSheet(
            "color: #666; font-size: 11px; padding: 4px;"
        )
        lay.addWidget(self.lbl_compute_mode)
        self._update_compute_mode_label()
        # Separator.
        lay.addSpacing(12)
        # ============ Appearance and language settings ============
        appearance_row = QWidget()
        appearance_layout = QGridLayout(appearance_row)
        appearance_layout.setContentsMargins(0, 0, 0, 0)
        appearance_layout.setHorizontalSpacing(8)
        appearance_layout.setVerticalSpacing(4)
        appearance_layout.setColumnStretch(0, 1)
        appearance_layout.setColumnStretch(1, 1)

        appearance_layout.addWidget(QLabel(tr("外观主题:")), 0, 0)
        self.theme_mode_combo = ComboBox()
        self.theme_mode_combo.setFixedHeight(36)
        self.theme_mode_combo.addItem(tr("跟随系统"), userData="auto")
        self.theme_mode_combo.addItem(tr("浅色"), userData="light")
        self.theme_mode_combo.addItem(tr("深色"), userData="dark")
        appearance_layout.addWidget(self.theme_mode_combo, 1, 0)

        appearance_layout.addWidget(QLabel(tr("界面语言:")), 0, 1)
        self.ui_language_combo = ComboBox()
        self.ui_language_combo.setFixedHeight(36)
        self.ui_language_combo.addItem(tr("跟随系统"), userData="auto")
        self.ui_language_combo.addItem(tr("简体中文"), userData="zh_CN")
        self.ui_language_combo.addItem("English", userData="en_US")
        appearance_layout.addWidget(self.ui_language_combo, 1, 1)
        lay.addWidget(appearance_row)
        # ============ Rendering Engine Settings ============
        lay.addWidget(QLabel(tr("公式渲染引擎:")))
        # Render engine selector; use qfluentwidgets ComboBox for consistent styling.
        self.render_engine_combo = ComboBox()
        self.render_engine_combo.setFixedHeight(36)
        # Add items.
        self.render_engine_combo.addItems(
            [
                tr("自动检测（推荐）"),
                tr("本地 MathJax"),
                "CDN MathJax",
                "LaTeX + pdflatex",
                "LaTeX + xelatex",
            ]
        )
        # Store the corresponding data.
        self._render_modes = [
            "auto",
            "mathjax_local",
            "mathjax_cdn",
            "latex_pdflatex",
            "latex_xelatex",
        ]
        lay.addWidget(self.render_engine_combo)
        # LaTeX options container; shown only when LaTeX is selected.
        self.latex_options_widget = QWidget()
        latex_layout = QVBoxLayout(self.latex_options_widget)
        latex_layout.setContentsMargins(0, 8, 0, 0)
        latex_layout.setSpacing(6)
        # LaTeX path selector.
        latex_path_layout = QHBoxLayout()
        latex_path_layout.addWidget(QLabel(tr("LaTeX 路径:")))
        self.latex_path_input = QLineEdit()
        self.latex_path_input.setPlaceholderText(
            tr("例：/Library/TeX/texbin/pdflatex")
            if sys.platform == "darwin"
            else tr("例：C:\\Program Files\\MiKTeX\\miktex\\bin\\x64\\pdflatex.exe")
        )
        self.latex_path_input.setFixedHeight(32)
        latex_path_layout.addWidget(self.latex_path_input)
        self.btn_browse_latex = PushButton(FluentIcon.FOLDER, tr("浏览"))
        self.btn_browse_latex.setFixedWidth(80)
        self.btn_browse_latex.setFixedHeight(32)
        latex_path_layout.addWidget(self.btn_browse_latex)
        latex_layout.addLayout(latex_path_layout)
        # LaTeX action buttons.
        latex_btn_layout = QHBoxLayout()
        self.btn_detect_latex = PushButton(FluentIcon.SEARCH, tr("自动检测"))
        self.btn_detect_latex.setFixedHeight(32)
        latex_btn_layout.addWidget(self.btn_detect_latex)
        self.btn_test_latex = PrimaryPushButton(tr("验证路径"))
        self.btn_test_latex.setFixedHeight(32)
        latex_btn_layout.addWidget(self.btn_test_latex)
        latex_layout.addLayout(latex_btn_layout)
        # LaTeX description.
        self.lbl_latex_desc = QLabel(
            tr("💡 需要本地安装 MacTeX 或 TeX Live，验证通过后才能使用")
            if sys.platform == "darwin"
            else tr("💡 需要本地安装 MiKTeX 或 TeX Live，验证通过后才能使用")
        )
        self.lbl_latex_desc.setStyleSheet("color: #666; font-size: 10px; padding: 4px;")
        self.lbl_latex_desc.setWordWrap(True)
        latex_layout.addWidget(self.lbl_latex_desc)
        self.latex_options_widget.setVisible(False)  # Hidden by default.
        lay.addWidget(self.latex_options_widget)
        # Check for updates.
        lay.addWidget(QLabel(tr("检查更新:")))
        self.btn_update = PushButton(FluentIcon.UPDATE, tr("检查更新"))
        self.btn_update.setFixedHeight(36)
        lay.addWidget(self.btn_update)
        # Startup behavior.
        lay.addWidget(QLabel(tr("启动行为:")))
        startup_row = QWidget()
        startup_layout = QHBoxLayout(startup_row)
        startup_layout.setContentsMargins(0, 0, 0, 0)
        startup_layout.setSpacing(6)
        self.runtime_log_button = PushButton(FluentIcon.DOCUMENT, tr("运行日志"))
        self.runtime_log_button.setFixedHeight(36)
        self.runtime_log_button.setCheckable(True)
        runtime_log_pref = False
        try:
            if self.parent() and hasattr(self.parent(), "cfg"):
                runtime_log_pref = self.parent().cfg.get("show_runtime_log", False)
        except Exception:
            runtime_log_pref = False
        self.runtime_log_button.setChecked(self._to_bool(runtime_log_pref))
        self.runtime_log_button.setToolTip(tr("启动后显示运行日志窗口"))
        startup_layout.addWidget(self.runtime_log_button, 1)
        self.automation_api_button = PushButton(
            FluentIcon.APPLICATION, tr("自动化接口")
        )
        self.automation_api_button.setFixedHeight(36)
        self.automation_api_button.setCheckable(True)
        automation_api_pref = False
        try:
            if self.parent() and hasattr(self.parent(), "cfg"):
                automation_api_pref = self.parent().cfg.get(
                    "automation_api_enabled", False
                )
        except Exception:
            automation_api_pref = False
        self.automation_api_button.setChecked(self._to_bool(automation_api_pref))
        self.automation_api_button.setToolTip(
            tr("允许 Office 插件、本机自动化工具及已授权远程设备调用 LaTeXSnipper")
        )
        startup_layout.addWidget(self.automation_api_button, 1)
        lay.addWidget(startup_row)
        self._sync_startup_action_buttons()
        # Separator.
        lay.addSpacing(8)
        # Advanced action: open terminal; use carefully.
        lay.addWidget(QLabel(tr("高级设置:")))
        terminal_row = QWidget()
        terminal_layout = QHBoxLayout(terminal_row)
        terminal_layout.setContentsMargins(0, 0, 0, 0)
        terminal_layout.setSpacing(6)
        self.access_scope_button = PushButton(FluentIcon.GLOBE, tr("访问范围"))
        self.access_scope_button.setFixedHeight(36)
        self.access_scope_button.setToolTip(
            tr("配置 Automation API 的本机或远程访问范围")
        )
        terminal_layout.addWidget(self.access_scope_button, 1)
        self.environment_terminal_button = PushButton(
            FluentIcon.COMMAND_PROMPT, tr("环境终端")
        )
        self.environment_terminal_button.setFixedHeight(36)
        self.environment_terminal_button.setToolTip(
            tr("打开主环境终端，可手动安装/修复依赖")
        )
        terminal_layout.addWidget(self.environment_terminal_button, 1)
        lay.addWidget(terminal_row)
        # Dependency management and model cache.
        deps_row = QWidget()
        deps_row_layout = QHBoxLayout(deps_row)
        deps_row_layout.setContentsMargins(0, 0, 0, 0)
        deps_row_layout.setSpacing(6)
        self.dependency_management_button = PushButton(
            FluentIcon.DEVELOPER_TOOLS, tr("依赖管理")
        )
        self.dependency_management_button.setFixedHeight(36)
        self.dependency_management_button.setToolTip(
            tr("打开依赖管理，可安装/修复依赖")
        )
        deps_row_layout.addWidget(self.dependency_management_button, 1)
        self.model_cache_button = PushButton(FluentIcon.FOLDER, tr("模型缓存"))
        self.model_cache_button.setFixedHeight(36)
        self.model_cache_button.setToolTip(tr("打开 MathCraft 模型缓存目录"))
        deps_row_layout.addWidget(self.model_cache_button, 1)
        lay.addWidget(deps_row)
        self.btn_cleanup_macos_local_data = None
        if sys.platform == "darwin":
            cleanup_row = QWidget()
            cleanup_row_layout = QHBoxLayout(cleanup_row)
            cleanup_row_layout.setContentsMargins(0, 0, 0, 0)
            cleanup_row_layout.setSpacing(6)
            self.btn_cleanup_macos_local_data = PushButton(
                FluentIcon.BROOM, tr("清理本机依赖与缓存")
            )
            self.btn_cleanup_macos_local_data.setFixedHeight(36)
            self.btn_cleanup_macos_local_data.setToolTip(
                tr("移除本机下载的依赖、缓存和日志；默认保留应用设置")
            )
            cleanup_row_layout.addWidget(self.btn_cleanup_macos_local_data, 1)
            lay.addWidget(cleanup_row)
        # Stretch spacer.
        lay.addStretch()
        # Connect signals.
        self.model_combo.currentIndexChanged.connect(self._on_model_combo_changed)
        self.compute_mode_probe_done.connect(self._on_compute_mode_probe_done)
        self._schedule_compute_mode_probe(force=True)
        self.btn_update.clicked.connect(lambda: check_update_dialog(self))
        self.environment_terminal_button.clicked.connect(
            self._open_environment_terminal
        )
        self.access_scope_button.clicked.connect(self._open_automation_access_dialog)
        self.dependency_management_button.clicked.connect(
            self._open_dependency_management
        )
        self.model_cache_button.clicked.connect(self._open_model_cache)
        if self.btn_cleanup_macos_local_data is not None:
            self.btn_cleanup_macos_local_data.clicked.connect(
                self._cleanup_macos_local_data
            )
        self.runtime_log_button.clicked.connect(self._on_runtime_log_button_clicked)
        self.automation_api_button.clicked.connect(
            self._on_automation_api_button_clicked
        )
        self.theme_mode_combo.currentIndexChanged.connect(self._on_theme_mode_changed)
        self.ui_language_combo.currentIndexChanged.connect(self._on_ui_language_changed)
        # Render-engine related signals.
        self.render_engine_combo.currentIndexChanged.connect(
            self._on_render_engine_changed
        )
        self.latex_path_test_done.connect(self._on_latex_path_test_done)
        self.latex_auto_detect_done.connect(self._on_latex_auto_detect_done)
        self.btn_browse_latex.clicked.connect(self._browse_latex_path)
        self.btn_detect_latex.clicked.connect(self._detect_latex)
        self.btn_test_latex.clicked.connect(self._test_latex_path)
        self.latex_path_input.textChanged.connect(self._on_latex_path_changed)
        self.external_apply_preset_btn.clicked.connect(self._apply_external_preset)
        self.external_test_btn.clicked.connect(self._test_external_model_connection)
        self.external_help_btn.clicked.connect(self._show_external_model_help)
        self.external_preset_combo.currentIndexChanged.connect(
            self._on_external_preset_changed
        )
        self.external_provider_combo.currentIndexChanged.connect(
            self._on_external_config_changed
        )
        self.external_provider_combo.currentIndexChanged.connect(
            self._on_external_provider_changed
        )
        self.external_prompt_combo.currentIndexChanged.connect(
            self._on_external_config_changed
        )
        self.external_base_url_input.textChanged.connect(
            self._on_external_config_changed
        )
        self.external_model_name_input.textChanged.connect(
            self._on_external_config_changed
        )
        self.external_api_key_input.textChanged.connect(
            self._on_external_config_changed
        )
        self.external_mineru_endpoint_input.textChanged.connect(
            self._on_external_config_changed
        )
        self.external_mineru_test_endpoint_input.textChanged.connect(
            self._on_external_config_changed
        )
        self.external_timeout_input.textChanged.connect(
            self._on_external_config_changed
        )
        self.external_custom_prompt_input.textChanged.connect(
            self._on_external_config_changed
        )
        # Initialize selection state.
        self._init_model_combo()
        self._update_model_desc()
        self._init_theme_mode_combo()
        self._init_ui_language_combo()
        self._init_render_engine()
        self._load_latex_settings()
        self.apply_theme_styles(force=True)

    def _to_bool(self, value) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return False

    def _sync_startup_action_buttons(self):
        if hasattr(self, "runtime_log_button") and self.runtime_log_button is not None:
            enabled = bool(self.runtime_log_button.isChecked())
            self.runtime_log_button.setText(
                tr("运行日志: 开") if enabled else tr("运行日志: 关")
            )
        if (
            hasattr(self, "automation_api_button")
            and self.automation_api_button is not None
        ):
            enabled = bool(self.automation_api_button.isChecked())
            self.automation_api_button.setText(
                tr("自动化接口: 开") if enabled else tr("自动化接口: 关")
            )

    def _on_runtime_log_button_clicked(self, _checked: bool):
        enabled = bool(self.runtime_log_button.isChecked())
        self._sync_startup_action_buttons()
        try:
            if self.parent() and hasattr(self.parent(), "cfg"):
                self.parent().cfg.set("show_runtime_log", enabled)
        except Exception:
            pass
        try:
            if self.parent() and hasattr(
                self.parent(), "apply_runtime_log_window_preference"
            ):
                self.parent().apply_runtime_log_window_preference(enabled)
        except Exception:
            pass
        self._show_info(tr("设置已保存"), tr("运行日志显示偏好已更新"), "success")

    def _on_automation_api_button_clicked(self, _checked: bool):
        enabled = bool(self.automation_api_button.isChecked())
        self.automation_api_button.setEnabled(False)
        self._sync_startup_action_buttons()

        def _done(ok: bool, message: str):
            self.automation_api_button.setEnabled(True)
            if not ok:
                self.automation_api_button.setChecked(False)
                self._sync_startup_action_buttons()
                self._show_info(
                    tr("自动化接口"),
                    tr("启用失败: {message}").format(message=message),
                    "error",
                )
                return
            self._sync_startup_action_buttons()
            self._show_info(tr("自动化接口"), message or tr("设置已更新"), "success")

        try:
            controller = (
                getattr(self.parent(), "automation_api", None)
                if self.parent()
                else None
            )
            if controller is not None:
                controller.set_automation_api_enabled_async(enabled, _done)
                return
            raise RuntimeError(tr("自动化接口控制器不可用"))
        except Exception as exc:
            _done(False, str(exc))

    def _open_automation_access_dialog(self):
        from ui.automation_access_dialog import AutomationAccessDialog

        parent = self.parent()
        if parent is None:
            return
        AutomationAccessDialog(parent, self).exec()

    def _update_model_desc(self):
        # Update model description.
        index = self.model_combo.currentIndex()
        if index < 0:
            return
        key, _ = self._model_options[index]
        descriptions = {
            "mathcraft": tr(
                "内置 MathCraft OCR，支持公式、混合、文字与 PDF 文档识别。"
            ),
            "external_model": tr(
                "连接多模态 OCR / VLM 接口，支持本地服务和部分线上服务。"
            ),
        }
        self.lbl_model_desc.setText(descriptions.get(key, ""))
