"""Main window construction mixin."""

from __future__ import annotations

import os
import sys

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget
from qfluentwidgets import FluentIcon, MessageBox, PushButton

from backend.model_factory import create_model_wrapper
from backend.platform import PlatformCapabilityRegistry
from bootstrap.deps_bootstrap import clear_deps_state
from preview.math_preview import build_math_html, get_mathjax_base_url
from runtime.app_paths import resource_path
from runtime.config_manager import ConfigManager, resolve_user_data_file
from runtime.dependency_bootstrap_controller import ensure_deps, show_dependency_wizard
from runtime.hotkey_config import normalize_hotkey_or_default
from runtime.webengine_runtime import ensure_webengine_loaded, get_webengine_view_class
from ui.theme_controller import apply_theme_mode, normalize_theme_mode, read_theme_mode_from_config
from ui.window_helpers import apply_app_window_icon as _apply_app_window_icon

DEFAULT_HISTORY_NAME = "history.json"
PLATFORM_DISABLE_GLOBAL_HOTKEY = False


class MainWindowSetupMixin:
    def __init__(self, startup_progress=None):
        super().__init__()
        self._startup_progress = startup_progress
        self._report_startup_progress("读取配置与启动参数...")
        self._pending_model_warmup_result = None
        self._model_warmup_result_signal.connect(self._apply_model_warmup_result)
        self._post_show_tasks_started = False
        self._startup_centered_once = False
        self._pending_hotkey_seq = None

        self.setWindowTitle("LaTeX Snipper")
        self.resize(1280, 760)
        self.setMinimumSize(1280, 760)

        self._force_exit = False

        self.model_status = "未加载"
        self.action_status = ""
        self._predict_busy = False
        self._last_recognition_cancel_notice_at = 0.0
        self.setAcceptDrops(True)
        self.overlay = None
        self._capture_start_pending = False
        self._capture_waiting_for_hidden_result_window = False
        self._last_capture_screen_index = None
        self._next_predict_result_screen_index = None
        self.predict_thread = None
        self.predict_worker = None
        self.pdf_predict_thread = None
        self.pdf_predict_worker = None
        self.pdf_progress = None
        self._pdf_output_format = None
        self._pdf_doc_style = None
        self._pdf_dpi = None
        self._pdf_structured_result = None
        self._pdf_result_window = None
        self._predict_result_dialog = None
        self._restore_predict_result_dialog_after_capture = None
        self._hidden_unpinned_predict_result_dialog_for_capture = None
        self._mathcraft_env_state = None
        self._last_capture_toast_ts = 0.0
        self.settings_window = None
        self.shortcut_window = None
        self.handwriting_window = None
        self.bilingual_pdf_window = None
        self._theme_is_dark_cached = None
        self._auto_theme_sync_in_progress = False
        self._auto_theme_refresh_timer = QTimer(self)
        self._auto_theme_refresh_timer.setSingleShot(True)
        self._auto_theme_refresh_timer.setInterval(160)
        self._auto_theme_refresh_timer.timeout.connect(self._on_auto_theme_refresh_timeout)
        self._model_warmup_in_progress = False
        self._model_warmup_notice_shown = False
        self._model_cache_repair_notice_shown = False
        self._preview_svg_cache = {}
        self._preview_svg_pending = set()
        self._preview_render_thread = None
        self._preview_render_worker = None
        self._model_warmup_callbacks = []


        self.cfg = ConfigManager()
        self._sanitize_model_config()
        self._theme_mode = normalize_theme_mode(self.cfg.get("theme_mode", "auto"))
        self.apply_app_theme_mode(self._theme_mode, refresh_preview=False)
        self.current_model = self.cfg.get("default_model", "mathcraft")
        self.desired_model = self.cfg.get("desired_model", "mathcraft")
        try:
            if self.desired_model == "mathcraft":
                preferred = self._get_preferred_model_for_predict()
                if preferred:
                    self.current_model = preferred
        except Exception:
            pass


        icon_path = resource_path("assets/icon.ico")
        self.icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()
        self.setWindowIcon(self.icon)


        self._report_startup_progress("正在加载主窗口组件...")
        try:
            self._report_startup_progress("正在初始化识别运行时...")

            self._apply_mathcraft_env()
            self.model = create_model_wrapper(self.current_model, auto_warmup=False)
            self.model.status_signal.connect(self.show_status_message)
            print("[DEBUG] ModelWrapper 初始化完成")


            self.model_status = "未加载"
            self._sync_current_model_status_from_preference()
            self._report_startup_progress("识别运行时已就绪，稍后后台预热")

        except Exception as e:
            app = QApplication.instance() or QApplication([])
            from PyQt6.QtWidgets import QMessageBox as QMsgBox
            apply_theme_mode(read_theme_mode_from_config())
            from PyQt6.QtGui import QFont
            font = QFont("Microsoft YaHei UI", 9)
            font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
            app.setFont(font)
            if isinstance(e, ModuleNotFoundError):

                clear_deps_state()
                QMsgBox.warning(
                    None, "依赖缺失",
                    "检测到依赖缺失，已重置状态文件。\n请重新选择安装目录并修复依赖。"
                )

                try:

                    result = ensure_deps(always_show_ui=True, require_layers=("BASIC", "CORE"))
                    if result == "_force_wizard":
                        print("[INFO] 检测到损坏环境，进入依赖修复向导。")
                        show_dependency_wizard(always_show_ui=True)
                    elif not result:
                        print("[WARN] 用户取消了依赖修复，程序退出。")
                        sys.exit(0)
                except Exception as ee:
                    print(f"[FATAL] ensure_deps 失败: {ee}")
                    show_dependency_wizard(always_show_ui=True)
                    return

            else:

                msg = MessageBox(
                    "错误",
                    f"模型初始化失败：{e}\n程序将进入依赖修复界面。",
                    self
                )
                _apply_app_window_icon(msg)
                msg.show()
                try:
                    ok = ensure_deps(always_show_ui=True, require_layers=("BASIC", "CORE"))
                    if not ok:
                        sys.exit(1)
                except Exception as ee:
                    print(f"[FATAL] ensure_deps 异常: {ee}")
                    show_dependency_wizard(always_show_ui=True)
                    return


        print("[DEBUG] 开始初始化历史记录")
        self._report_startup_progress("正在初始化历史记录...")
        self.history_path = resolve_user_data_file(self.cfg, "history_path", DEFAULT_HISTORY_NAME)
        self.history = []


        print("[DEBUG] 开始初始化状态栏")
        self._report_startup_progress("正在初始化状态栏...")
        self.status_label = QLabel()
        self.refresh_status_label()


        self.favorites_window = None
        self._report_startup_progress("初始化平台能力与快捷键...")
        self.platform_registry = PlatformCapabilityRegistry(
            parent=self,
            disable_global_hotkey=PLATFORM_DISABLE_GLOBAL_HOTKEY,
        )
        self.platform_providers = self.platform_registry.create()
        self.hotkey_provider = self.platform_providers.hotkey
        self.screenshot_provider = self.platform_providers.screenshot
        self.system_provider = self.platform_providers.system
        if self.hotkey_provider.activated is not None:
            self.hotkey_provider.activated.connect(self.on_hotkey_triggered)
        seq = normalize_hotkey_or_default(self.cfg.get("hotkey", "Ctrl+F"))
        self._pending_hotkey_seq = seq

        self._report_startup_progress("构建主窗口界面...")


        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(6, 6, 6, 6)
        left_layout.setSpacing(8)


        self.capture_button = PushButton(FluentIcon.SEARCH, "截图识别")
        self.capture_button.setFixedHeight(40)
        self.capture_button.clicked.connect(self.start_capture)
        left_layout.addWidget(self.capture_button)


        history_header = QHBoxLayout()
        history_header.setContentsMargins(0, 0, 0, 0)
        history_header.setSpacing(6)
        self.history_title_label = QLabel("历史记录")
        history_header.addWidget(self.history_title_label)
        history_header.addStretch()
        self.history_reverse = bool(self.cfg.get("history_reverse", True))
        self.history_order_button = PushButton("最新在前" if self.history_reverse else "最早在前")
        self.history_order_button.setFixedHeight(28)
        self.history_order_button.clicked.connect(self.toggle_history_order)
        history_header.addWidget(self.history_order_button)
        left_layout.addLayout(history_header)


        self.history_scroll = QScrollArea()
        self.history_scroll.setWidgetResizable(True)
        self.history_container = QWidget()
        self.history_layout = QVBoxLayout(self.history_container)
        self.history_layout.setContentsMargins(0, 0, 0, 0)
        self.history_layout.setSpacing(6)
        self.history_layout.addStretch()
        self.history_scroll.setWidget(self.history_container)
        left_layout.addWidget(self.history_scroll, 1)


        btn_row = QHBoxLayout()
        self.clear_history_button = PushButton(FluentIcon.DELETE, "清空")
        self.change_key_button = PushButton(FluentIcon.CLIPPING_TOOL, "快捷键")
        self.show_fav_button = PushButton(FluentIcon.HEART, "收藏夹")
        self.settings_button = PushButton(FluentIcon.SETTING, "设置")
        self.clear_history_button.clicked.connect(self.clear_history)
        self.change_key_button.clicked.connect(self.set_shortcut)
        self.show_fav_button.clicked.connect(self.open_favorites)
        self.settings_button.clicked.connect(self.open_settings)
        btn_row.addWidget(self.clear_history_button)
        btn_row.addWidget(self.change_key_button)
        btn_row.addWidget(self.show_fav_button)
        btn_row.addWidget(self.settings_button)
        left_layout.addLayout(btn_row)

        left_layout.addWidget(self.status_label)


        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(6, 6, 6, 6)
        right_layout.setSpacing(8)


        editor_header = QHBoxLayout()
        editor_header.setContentsMargins(0, 0, 0, 0)
        editor_header.setSpacing(0)
        self.editor_title_label = QLabel("LaTeX 编辑器")
        editor_header.addWidget(self.editor_title_label)
        editor_header.addSpacing(6)
        self.upload_image_btn = PushButton(FluentIcon.PHOTO, "图片识别")
        self.upload_image_btn.clicked.connect(self._upload_image_recognition)
        self.upload_pdf_btn = PushButton(FluentIcon.DOCUMENT, "PDF识别")
        self.upload_pdf_btn.clicked.connect(self._upload_pdf_recognition)
        try:
            img_exts = self._get_supported_image_extensions()
            self.upload_image_btn.setToolTip("支持格式: " + ", ".join(img_exts))
        except Exception:
            pass
        self.upload_pdf_btn.setToolTip("支持格式: PDF")
        self.copy_editor_btn = PushButton(FluentIcon.COPY, "复制")
        self.copy_editor_btn.clicked.connect(self._copy_editor_content)
        self.export_btn = PushButton(FluentIcon.SHARE, "导出")
        self.export_btn.clicked.connect(self._show_export_menu)
        self.handwriting_btn = PushButton(FluentIcon.FINGERPRINT, "手写识别")
        self.handwriting_btn.clicked.connect(self.open_handwriting_window)
        self.bilingual_reading_btn = PushButton(FluentIcon.BOOK_SHELF, "双语阅读")
        self.bilingual_reading_btn.clicked.connect(self.open_bilingual_reader)
        self.workbench_btn = PushButton(FluentIcon.PROJECTOR, "数学工作台")
        self.workbench_btn.clicked.connect(self.open_workbench)
        editor_actions = QHBoxLayout()
        editor_actions.setContentsMargins(0, 0, 0, 0)
        editor_actions.setSpacing(6)
        editor_actions.addWidget(self.upload_image_btn)
        editor_actions.addWidget(self.upload_pdf_btn)
        editor_actions.addWidget(self.handwriting_btn)
        editor_actions.addWidget(self.copy_editor_btn)
        editor_actions.addWidget(self.export_btn)
        editor_actions.addWidget(self.bilingual_reading_btn)
        editor_actions.addWidget(self.workbench_btn)
        editor_header.addLayout(editor_actions)
        right_layout.addLayout(editor_header)


        from qfluentwidgets import PlainTextEdit
        self.latex_editor = PlainTextEdit()
        self.latex_editor.setPlaceholderText("在此输入 LaTeX 公式，下方将实时渲染...")
        self.latex_editor.setMinimumHeight(100)
        self.latex_editor.setMaximumHeight(150)
        right_layout.addWidget(self.latex_editor)


        preview_header = QHBoxLayout()
        self.preview_title_label = QLabel("实时渲染预览")
        preview_header.addWidget(self.preview_title_label)
        preview_header.addStretch()
        self.clear_preview_btn = PushButton(FluentIcon.BROOM, "清空预览")
        self.clear_preview_btn.clicked.connect(self._clear_preview)
        preview_header.addWidget(self.clear_preview_btn)
        right_layout.addLayout(preview_header)


        self._report_startup_progress("初始化公式预览引擎...")
        self.preview_view = None
        self._render_timer = None
        self._pending_latex = ""
        self._rendered_formulas = []
        self._formula_names = {}
        self._formula_types = {}
        webengine_view_cls = get_webengine_view_class() if ensure_webengine_loaded() else None
        if webengine_view_cls is not None:
            self.preview_view = webengine_view_cls()


            try:
                from PyQt6.QtWebEngineCore import QWebEngineSettings
                settings = self.preview_view.settings()
                settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
                settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
            except Exception:
                pass

            self.preview_view.setMinimumHeight(200)
            try:
                self.preview_view.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)
            except Exception:
                pass

            try:
                pg = self.preview_view.page()
                pg.loadStarted.connect(lambda: None)
                pg.loadFinished.connect(lambda ok: print(f"[WebEngine] loadFinished ok={ok}"))
                pg.renderProcessTerminated.connect(lambda status, code: print(f"[WebEngine] renderProcessTerminated status={status} code={code}"))
            except Exception:
                pass

            html = build_math_html("")
            base_url = get_mathjax_base_url()

            try:
                self.preview_view.setHtml(html, base_url)
            except Exception:
                pass
            right_layout.addWidget(self.preview_view, 1)


            self._render_timer = QTimer(self)
            self._render_timer.setSingleShot(True)
            self._render_timer.timeout.connect(self._do_render_latex)


            self.latex_editor.textChanged.connect(self._on_editor_text_changed)
        else:

            self.preview_fallback_label = QLabel("WebEngine 未加载，无法渲染公式预览。\n请确保已安装 PyQtWebEngine。")
            self.preview_fallback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            right_layout.addWidget(self.preview_fallback_label, 1)


        from PyQt6.QtWidgets import QSplitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([420, 900])
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)

        container = QWidget()
        for drop_target in (
            left_panel,
            right_panel,
            splitter,
            container,
            self.latex_editor,
            self.preview_view,
            getattr(self, "preview_fallback_label", None),
        ):
            self._enable_file_drop_target(drop_target)
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(splitter)


        self.setCentralWidget(container)


        self._report_startup_progress("初始化系统托盘与历史记录...")
        self.tray_icon = self.system_provider.create_tray(self.icon, self)
        self.update_tray_tooltip()
        try:
            from PyQt6.QtGui import QGuiApplication

            qapp = QGuiApplication.instance()
            if qapp is not None:
                qapp.screenAdded.connect(lambda _screen: QTimer.singleShot(0, self.update_tray_menu))
                qapp.screenRemoved.connect(lambda _screen: QTimer.singleShot(0, self.update_tray_menu))
        except Exception:
            pass

        self.load_history()
        self.update_history_ui()
        self.refresh_status_label()



        self.update_tray_menu()

        self._apply_primary_buttons()
        self._apply_theme_styles(force=True)
        QApplication.instance().aboutToQuit.connect(self._graceful_shutdown)

        self._update_editor_labels_for_render_mode()

    def _on_render_mode_changed(self, mode: str) -> None:
        """Handle render mode changes from the settings window."""
        self._update_editor_labels_for_render_mode()

    def _update_editor_labels_for_render_mode(self) -> None:
        """Update editor title label and placeholder based on the current render mode."""
        try:
            from backend.latex_renderer import get_document_render_mode

            is_typst = get_document_render_mode() == "typst"
        except Exception:
            is_typst = False

        if is_typst:
            self.editor_title_label.setText("Typst 编辑器")
            self.latex_editor.setPlaceholderText("在此输入 Typst 公式，下方将实时渲染...")
        else:
            self.editor_title_label.setText("LaTeX 编辑器")
            self.latex_editor.setPlaceholderText("在此输入 LaTeX 公式，下方将实时渲染...")
