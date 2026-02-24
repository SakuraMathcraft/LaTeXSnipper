import os, sys, subprocess
from pathlib import Path
import time
import pyperclip
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtWidgets import (QDialog, QLineEdit, QVBoxLayout, QLabel, QHBoxLayout, QWidget, QFileDialog, QInputDialog, QMessageBox, QCheckBox)
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


def _subprocess_creationflags() -> int:
    if os.name != "nt":
        return 0
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))


class SettingsWindow(QDialog):
    """设置窗口 - 使用 QDialog 作为基类"""
    model_changed = pyqtSignal(str)
    env_torch_probe_done = pyqtSignal(str, object, str)
    pix2text_pkg_probe_done = pyqtSignal(bool)
    def __init__(self, parent=None):
        super().__init__(parent)
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
        self.resize(620, 320)
        self.setMinimumWidth(620)
        lay = QVBoxLayout(self)
        lay.setSpacing(8)
        lay.setContentsMargins(16, 16, 16, 16)
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
        # 模型选择区域
        lay.addWidget(QLabel("选择识别模式:"))
        # 使用下拉框支持更多识别模式
        from qfluentwidgets import ComboBox
        self.model_combo = ComboBox()
        self.model_combo.setFixedHeight(36)
        # 添加识别模式选项
        # 添加识别模式选项
        # 添加识别模式选项
        self._model_options = [
            ("pix2text", "pix2text - 公式识别"),
        ]
        for key, label in self._model_options:
            self.model_combo.addItem(label, userData=key)
        lay.addWidget(self.model_combo)
        # 模式说明
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
        pix2text_env_layout.addWidget(self.pix2text_pyexe_input)
        self.pix2text_pyexe_browse = PushButton(FluentIcon.FOLDER, "浏览")
        self.pix2text_pyexe_browse.setFixedHeight(30)
        self.pix2text_pyexe_browse.clicked.connect(self._on_pix2text_pyexe_browse)
        pix2text_env_layout.addWidget(self.pix2text_pyexe_browse)
        self.pix2text_pyexe_clear = PushButton(FluentIcon.DELETE, "清除")
        self.pix2text_pyexe_clear.setFixedHeight(30)
        self.pix2text_pyexe_clear.clicked.connect(self._on_pix2text_pyexe_clear)
        pix2text_env_layout.addWidget(self.pix2text_pyexe_clear)
        self.pix2text_pyexe_create = PushButton(FluentIcon.DEVELOPER_TOOLS, "一键创建")
        self.pix2text_pyexe_create.setFixedHeight(30)
        self.pix2text_pyexe_create.clicked.connect(self._on_pix2text_pyexe_create)
        pix2text_env_layout.addWidget(self.pix2text_pyexe_create)
        lay.addWidget(self.pix2text_env_widget)
        self.pix2text_env_hint = QLabel("提示：v1.05 起 pix2text 与主依赖环境统一，不再使用隔离环境。")
        self.pix2text_env_hint.setStyleSheet("color: #666; font-size: 10px; padding: 2px;")
        self.pix2text_env_hint.setWordWrap(True)
        lay.addWidget(self.pix2text_env_hint)
        # pix2text 推理设备检测
        self.pix2text_torch_status = QLabel("pix2text 设备: 未检测")
        self.pix2text_torch_status.setStyleSheet("color: #666; font-size: 10px; padding: 2px;")
        self.pix2text_torch_status.setWordWrap(True)
        lay.addWidget(self.pix2text_torch_status)
        # v1.05: 安装/下载统一收敛到依赖向导，设置页不再提供模型下载/安装入口。
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
        # v1.05: 彻底移除 UniMERNet UI（仅保留 pix2text）。
        self.unimernet_widget = None
        self.unimernet_env_widget = None
        self.unimernet_env_hint = None
        self.unimernet_torch_status = None
        self.unimernet_torch_btn_row = None
        # v1.05: 不再支持隔离环境创建/选择，固定使用主依赖环境 python。
        self.pix2text_pyexe_browse.hide()
        self.pix2text_pyexe_clear.hide()
        self.pix2text_pyexe_create.hide()
        self.pix2text_pyexe_input.setReadOnly(True)
        self.lbl_compute_mode = QLabel()
        self.lbl_compute_mode.setStyleSheet("color: #666; font-size: 11px; padding: 4px;")
        lay.addWidget(self.lbl_compute_mode)
        self._update_compute_mode_label()
        # 分隔
        lay.addSpacing(12)
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
        # LaTeX 编译器选择
        latex_compiler_layout = QHBoxLayout()
        latex_compiler_layout.addWidget(QLabel("编译器:"))
        from qfluentwidgets import ComboBox as FluentComboBox
        self.latex_compiler_combo = FluentComboBox()
        self.latex_compiler_combo.setFixedHeight(32)
        self.latex_compiler_combo.addItems(["pdflatex", "xelatex"])
        latex_compiler_layout.addWidget(self.latex_compiler_combo)
        latex_layout.addLayout(latex_compiler_layout)
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
        # 渲染引擎相关信号
        self.render_engine_combo.currentIndexChanged.connect(self._on_render_engine_changed)
        self.btn_browse_latex.clicked.connect(self._browse_latex_path)
        self.btn_detect_latex.clicked.connect(self._detect_latex)
        self.btn_test_latex.clicked.connect(self._test_latex_path)
        self.latex_path_input.textChanged.connect(self._on_latex_path_changed)
        # 初始化选择状态
        self._init_model_combo()
        self._update_model_desc()
        self._init_render_engine()
        self._load_latex_settings()
        # 编译器切换时自动切换路径
        if hasattr(self, 'latex_compiler_combo'):
            self.latex_compiler_combo.currentIndexChanged.connect(self._on_latex_compiler_changed)
        # 后台预热探测缓存，减少首次点击“终端/安装GPU”卡顿
        QTimer.singleShot(120, self._warm_probe_cache_async)

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
    def _on_latex_compiler_changed(self):
        """切换 LaTeX 编译器时自动切换路径"""
        idx = self.latex_compiler_combo.currentIndex()
        current_path = self.latex_path_input.text().strip()
        import os
        # 仅在路径为空或为另一编译器默认名时自动切换
        pdflatex_name = "pdflatex.exe"
        xelatex_name = "xelatex.exe"
        # 判断当前路径是否为 pdflatex 或 xelatex
        if idx == 0:
            # 选择 pdflatex
            if (not current_path) or os.path.basename(current_path).lower() == xelatex_name:
                # 自动切换为 pdflatex
                if current_path:
                    new_path = os.path.join(os.path.dirname(current_path), pdflatex_name)
                else:
                    new_path = pdflatex_name
                self.latex_path_input.setText(new_path)
        else:
            # 选择 xelatex
            if (not current_path) or os.path.basename(current_path).lower() == pdflatex_name:
                if current_path:
                    new_path = os.path.join(os.path.dirname(current_path), xelatex_name)
                else:
                    new_path = xelatex_name
                self.latex_path_input.setText(new_path)
        # 触发路径变更逻辑（如按钮状态等）
        self._on_latex_path_changed()
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
        try:
            from backend.torch_runtime import mode_satisfies

            main_info, _main_py = self._get_main_torch_info_cached(allow_block=True)
            if mode_satisfies(main_info, mode):
                main_mode = (main_info.get("mode") or mode).upper()
                main_ver = main_info.get("torch_version", "") or "unknown"
                reuse_note = f"已复用主环境 PyTorch（{main_mode}, ver={main_ver}），隔离环境无需重复安装 torch。"
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
        except Exception:
            # fallback to legacy command generation
            extra_index = " --extra-index-url https://pypi.org/simple"
            if mode == "gpu":
                gpu_plan = self._detect_torch_gpu_plan()
                if not gpu_plan:
                    note = getattr(self, "_cuda_detect_note", "")
                    title = "CUDA 版本不支持" if "低于 11.8" in note else "CUDA 未检测到"
                    self._show_info(title, f"{note}。请先安装 CUDA Toolkit，或改装 CPU 版本。", "warning")
                    return
                selected_gpu_tag = str(gpu_plan.get("tag", "") or "")
                torch_cmd = (
                    f"\"{pyexe}\" -m pip install "
                    f"torch=={gpu_plan['torch']} torchvision=={gpu_plan['vision']} torchaudio=={gpu_plan['audio']} "
                    f"--index-url https://download.pytorch.org/whl/{gpu_plan['tag']}{extra_index}"
                )
            else:
                cpu_plan = self._torch_cpu_plan()
                torch_cmd = (
                    f"\"{pyexe}\" -m pip install "
                    f"torch=={cpu_plan['torch']} torchvision=={cpu_plan['vision']} torchaudio=={cpu_plan['audio']} "
                    f"--index-url https://download.pytorch.org/whl/cpu{extra_index}"
                )

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
            lead_msg = f"将在隔离环境安装 {mode.upper()} 版 PyTorch：\n\n"
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
        self._update_pix2text_visibility()
    def _on_model_combo_changed(self, index: int):
        # 模型下拉框选择变化
        if index < 0 or index >= len(self._model_options):
            return
        key, _ = self._model_options[index]
        if self._is_pix2text_ready():
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
    def _on_pix2text_pyexe_browse(self):
        self._show_info("已固定", "pix2text 使用主依赖环境，无需单独选择 python.exe。", "info")
    def _on_pix2text_pyexe_clear(self):
        self._show_info("已固定", "pix2text 使用主依赖环境，无需清除独立环境。", "info")
    def _on_pix2text_pyexe_create(self):
        self._show_info("已固定", "v1.05 起不再创建模型隔离环境，统一使用主依赖环境。", "info")
    def _update_pix2text_visibility(self):
        key = None
        idx = self.model_combo.currentIndex()
        if idx >= 0 and idx < len(self._model_options):
            key, _ = self._model_options[idx]
        visible = (key == "pix2text")
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
            if visible:
                if not pyexe_exists:
                    self.pix2text_env_hint.setText("⚠️ 主依赖环境未就绪，请先运行依赖向导。")
                elif not ready:
                    self.pix2text_env_hint.setText("⚠️ pix2text 未部署：请先打开【依赖管理向导】安装依赖。")
                else:
                    self.pix2text_env_hint.setText("💡 pix2text 已部署，可选择识别类型。")
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
        """渲染引擎改变 - 立即验证并测试"""
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
            # LaTeX 模式：先尝试自动检测
            from backend.latex_renderer import LaTeXRenderer
            latex_path = self.latex_path_input.text().strip()
            if not latex_path:
                # 尝试自动检测
                renderer = LaTeXRenderer()
                if renderer.is_available():
                    latex_path = renderer.latex_cmd
                    self.latex_path_input.setText(latex_path)
                    print(f"[LaTeX] 自动检测成功: {latex_path}")
                else:
                    # 检测失败，显示浮动通知并恢复
                    self._show_notification("warning", "未检测到 LaTeX", 
                                          "请点击浏览选择路径或安装 MiKTeX/TeX Live")
                    self.render_engine_combo.setCurrentIndex(0)
                    return
            # 立即测试 LaTeX
            self._test_latex_path()
        else:
            # 非 LaTeX 模式：直接保存（无需确认弹窗）
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
        """自动检测 LaTeX"""
        from backend.latex_renderer import LaTeXRenderer
        renderer = LaTeXRenderer()  # 会自动检测
        if renderer.is_available():
            self.latex_path_input.setText(renderer.latex_cmd)
            self._save_latex_settings()
            self._show_notification("success", "检测成功", f"检测到 LaTeX:\n{renderer.latex_cmd}")
        else:
            self._show_notification("warning", "检测失败", 
                                  "未检测到 LaTeX。请安装 MiKTeX/TeX Live 或手动指定路径")
    def _save_latex_settings(self):
        """保存 LaTeX 设置"""
        try:
            from backend.latex_renderer import _latex_settings
            if _latex_settings:
                latex_path = self.latex_path_input.text().strip()
                use_xelatex = self.latex_compiler_combo.currentIndex() == 1
                if latex_path:
                    _latex_settings.set_latex_path(latex_path)
                    _latex_settings.settings["use_xelatex"] = use_xelatex
                    _latex_settings.save()
                    print(f"[LaTeX] 设置已保存: {latex_path}")
        except Exception as e:
            print(f"[WARN] 保存 LaTeX 设置失败: {e}")
    def _test_latex_path(self):
        """测试 LaTeX 路径并验证是否可用"""
        from backend.latex_renderer import LaTeXRenderer
        latex_path = self.latex_path_input.text().strip()
        if not latex_path:
            self._show_notification("error", "路径为空", "请输入 LaTeX 路径或点击自动检测")
            return False
        try:
            # 创建 LaTeX 渲染器来验证路径
            renderer = LaTeXRenderer(latex_path)
            if not renderer.is_available():
                self._show_notification("error", "路径无效", "找不到 LaTeX 可执行文件")
                return False
            # 测试渲染简单公式
            print(f"[LaTeX] 测试路径: {latex_path}")
            test_svg = renderer.render_to_svg(r"\frac{1}{2} + \frac{1}{3} = \frac{5}{6}")
            if test_svg and len(test_svg) > 100:  # SVG 应该有合理的长度
                self.btn_test_latex.setText("✓ 已验证")
                self.btn_test_latex.setEnabled(False)
                self._show_notification("success", "验证成功", "LaTeX 环境已就绪")
                # 保存设置
                self._save_latex_settings()
                # 获取当前选择的渲染模式
                current_index = self.render_engine_combo.currentIndex()
                if current_index >= 0 and current_index < len(self._render_modes):
                    engine = self._render_modes[current_index]
                    self._save_render_mode(engine)
                return True
            else:
                self._show_notification("error", "验证失败", "无法用该路径渲染公式，请检查安装")
                return False
        except Exception as e:
            print(f"[ERROR] LaTeX 验证失败: {e}")
            self._show_notification("error", "验证出错", str(e)[:100])
            return False
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
                _latex_settings.save()
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
            "pix2text": "高精度公式识别，支持公式/混合/文字/整页/表格与 PDF 识别。",
        }
        desc = descriptions.get(key, "")
        if key == "pix2text":
            desc += "\n提示：v1.05 起仅保留 pix2text，依赖统一由主环境管理。"
        self.lbl_model_desc.setText(desc)
    def _open_terminal(self, env_key: str | None = None):
        if isinstance(env_key, bool):
            env_key = None
        import subprocess
        import os
        from qfluentwidgets import MessageBox, InfoBar, InfoBarPosition
        if env_key is None:
            env_key = self._get_terminal_env_key()
        # v1.05: 统一只打开主环境终端。
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
            "echo   - v1.05 keeps pix2text only",
            "echo   - use unified main env; no model-isolated env",
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
        from deps_bootstrap import ensure_deps, needs_restart_for_install
        from qfluentwidgets import InfoBar, InfoBarPosition, MessageBox
        # 检测是否有冲突模块已加载
        need_restart, loaded_mods = needs_restart_for_install()
        if need_restart:
            # 有模块已加载，提示用户重启
            mod_list = ", ".join(loaded_mods[:5])
            if len(loaded_mods) > 5:
                mod_list += f" 等 {len(loaded_mods)} 个模块"
            msg = MessageBox(
                "检测到模块冲突",
                f"• 以下模块已被程序加载:{mod_list}\n"
                "• 这可能导致依赖安装失败(文件被占用)\n"
                "• 建议重启程序并直接打开向导。是否立即重启？\n"
                "• ESC取消操作",
                self
            )
            msg.yesButton.setText("重启程序")
            msg.cancelButton.setText("继续安装")
            # ESC 键检测：用户按 ESC 不执行任何操作
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
            # 如果用户按 ESC，直接返回不执行任何操作
            if esc_pressed[0]:
                return
            if result:
                # 用户选择重启
                self._restart_with_wizard()
                return
            # 用户选择继续，显示警告
            InfoBar.warning(
                title="注意",
                content="如遇安装失败，请关闭程序后手动安装",
                parent=self.parent() if self.parent() else None,
                duration=5000,
                position=InfoBarPosition.TOP
            )
        # 关闭当前设置窗口
        self.close()
        # 强制显示向导界面（always_show_ui=True, from_settings=True）
        try:
            ok = ensure_deps(prompt_ui=True, always_show_ui=True, from_settings=True, force_verify=True)
            if ok:
                InfoBar.success(
                    title="提示",
                    content="依赖安装完成，部分更改可能需要重启程序生效。",
                    parent=self.parent() if self.parent() else None,
                    duration=5000,
                    position=InfoBarPosition.TOP
                )
        except Exception as e:
            InfoBar.error(
                title="错误",
                content=f"依赖向导出错: {e}",
                parent=self.parent() if self.parent() else None,
                duration=5000,
                position=InfoBarPosition.TOP
            )
    def _restart_with_wizard(self):
        """重启程序并打开依赖向导"""
        import subprocess
        import sys
        import os
        from PyQt6.QtWidgets import QApplication
        # 设置环境变量，让新进程知道要打开向导
        env = os.environ.copy()
        env["LATEXSNIPPER_OPEN_WIZARD"] = "1"
        env["LATEXSNIPPER_FORCE_VERIFY"] = "1"
        env["LATEXSNIPPER_RESTART"] = "1"
        # 避免新进程被“依赖已就绪”短路
        env.pop("LATEXSNIPPER_DEPS_OK", None)
        # 获取当前 Python 和脚本路径
        python_exe = sys.executable
        script_path = os.path.abspath(sys.argv[0])
        base_flags = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        spawn_flags = base_flags | int(_subprocess_creationflags())
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
            # 启动新进程
            if script_path.endswith('.py'):
                subprocess.Popen(
                    [python_exe, script_path, "--force-deps-check"],
                    env=env,
                    creationflags=spawn_flags
                )
            else:
                # 打包后的 exe
                subprocess.Popen(
                    [script_path, "--force-deps-check"],
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
    def select_model(self, model_name: str):
        # 只发射信号，由信号连接的 on_model_changed 处理
        self.model_changed.emit(model_name)
        self.update_model_selection()
        self._update_compute_mode_label()
    def _update_compute_mode_label(self):
        """更新计算模式状态标签"""
        try:
            import torch
            cuda_available = torch.cuda.is_available()
            if cuda_available:
                gpu_name = torch.cuda.get_device_name(0)
                self.lbl_compute_mode.setText(f"🟢 GPU 可用: {gpu_name}")
                self.lbl_compute_mode.setStyleSheet("color: #2e7d32; font-size: 11px; padding: 4px;")
            else:
                self.lbl_compute_mode.setText("🟡 仅 CPU 模式 (未检测到 GPU层依赖)")
                self.lbl_compute_mode.setStyleSheet("color: #f57c00; font-size: 11px; padding: 4px;")
        except Exception:
            self.lbl_compute_mode.setText("⚪ 计算模式未知")
            self.lbl_compute_mode.setStyleSheet("color: #666; font-size: 11px; padding: 4px;")
    def update_model_selection(self):
        # sync model combo selection state
        for i, (key, _) in enumerate(self._model_options):
            if key == "pix2text":
                self.model_combo.blockSignals(True)
                self.model_combo.setCurrentIndex(i)
                self.model_combo.blockSignals(False)
                break
        self._init_pix2text_mode()
        self._update_model_desc()
        self._update_pix2text_visibility()
# ---------------- 主窗口 ----------------
from PyQt6.QtCore import Qt

