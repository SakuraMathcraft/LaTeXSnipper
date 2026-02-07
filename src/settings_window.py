import os, sys, subprocess
from pathlib import Path
import pyperclip
from PyQt6.QtCore import Qt, QUrl, pyqtSignal, QTimer
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (QDialog, QLineEdit, QVBoxLayout, QLabel, QHBoxLayout, QWidget, QComboBox, QFileDialog, QInputDialog, QMessageBox)
from qfluentwidgets import FluentIcon, PushButton, PrimaryPushButton, ComboBox, InfoBar, InfoBarPosition, MessageBox
from updater import check_update_dialog
from deps_bootstrap import custom_warning_dialog
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
        self.resize(340, 320)
        lay = QVBoxLayout(self)
        lay.setSpacing(8)
        lay.setContentsMargins(16, 16, 16, 16)
        self._pix2text_pkg_ready = False
        self._torch_probe_seq = {"pix2text": 0, "unimernet": 0}
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
            ("pix2tex", "pix2tex - 公式识别（轻量）"),
            ("pix2text", "pix2text - 公式识别（高精度）"),
            ("unimernet", "UniMERNet - 强化公式识别（实验）"),
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
        pix2text_env_layout.addWidget(QLabel("pix2text 环境:"))
        self.pix2text_pyexe_input = QLineEdit()
        self.pix2text_pyexe_input.setPlaceholderText("选择 pix2text 隔离环境 python.exe")
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
        self.pix2text_env_hint = QLabel("提示：建议 pix2text 使用独立环境，避免与 pix2tex 冲突。")
        self.pix2text_env_hint.setStyleSheet("color: #666; font-size: 10px; padding: 2px;")
        self.pix2text_env_hint.setWordWrap(True)
        lay.addWidget(self.pix2text_env_hint)
        # pix2text 推理设备检测
        self.pix2text_torch_status = QLabel("pix2text 设备: 未检测")
        self.pix2text_torch_status.setStyleSheet("color: #666; font-size: 10px; padding: 2px;")
        self.pix2text_torch_status.setWordWrap(True)
        lay.addWidget(self.pix2text_torch_status)
        self.pix2text_torch_btn_row = QWidget()
        pix2text_torch_btn_layout = QHBoxLayout(self.pix2text_torch_btn_row)
        pix2text_torch_btn_layout.setContentsMargins(0, 0, 0, 0)
        pix2text_torch_btn_layout.setSpacing(6)
        self.pix2text_torch_install_gpu = PushButton(FluentIcon.SETTING, "安装/切换 GPU 版本")
        self.pix2text_torch_install_gpu.setFixedHeight(30)
        self.pix2text_torch_install_gpu.clicked.connect(lambda: self._install_env_torch("pix2text", "gpu"))
        pix2text_torch_btn_layout.addWidget(self.pix2text_torch_install_gpu)
        self.pix2text_torch_reinstall = PushButton(FluentIcon.SYNC, "重装")
        self.pix2text_torch_reinstall.setFixedHeight(30)
        self.pix2text_torch_reinstall.clicked.connect(lambda: self._reinstall_env_torch("pix2text"))
        pix2text_torch_btn_layout.addWidget(self.pix2text_torch_reinstall)
        self.pix2text_torch_refresh = PushButton(FluentIcon.UPDATE, "刷新检测")
        self.pix2text_torch_refresh.setFixedHeight(30)
        self.pix2text_torch_refresh.clicked.connect(lambda: self._refresh_env_status("pix2text"))
        pix2text_torch_btn_layout.addWidget(self.pix2text_torch_refresh)
        lay.addWidget(self.pix2text_torch_btn_row)
        # pix2text 部署/下载
        self.pix2text_dl_widget = QWidget()
        pix2text_dl_layout = QHBoxLayout(self.pix2text_dl_widget)
        pix2text_dl_layout.setContentsMargins(0, 0, 0, 0)
        pix2text_dl_layout.setSpacing(6)
        self.pix2text_download_btn = PushButton(FluentIcon.DOWNLOAD, "下载模型(默认CPU)")
        self.pix2text_download_btn.setFixedHeight(30)
        self.pix2text_download_btn.clicked.connect(self._on_pix2text_download_clicked)
        pix2text_dl_layout.addWidget(self.pix2text_download_btn)
        self.pix2text_open_btn = PushButton(FluentIcon.GLOBE, "打开缓存目录")
        self.pix2text_open_btn.setFixedHeight(30)
        self.pix2text_open_btn.clicked.connect(self._on_pix2text_open_download_clicked)
        pix2text_dl_layout.addWidget(self.pix2text_open_btn)
        lay.addWidget(self.pix2text_dl_widget)
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
        # UniMERNet 模型权重选择
        self.unimernet_widget = QWidget()
        unimernet_layout = QHBoxLayout(self.unimernet_widget)
        unimernet_layout.setContentsMargins(0, 0, 0, 0)
        unimernet_layout.setSpacing(6)
        unimernet_layout.addWidget(QLabel("UniMERNet 模型权重:"))
        self.unimernet_combo = ComboBox()
        self.unimernet_combo.setFixedHeight(30)
        self.unimernet_combo.addItem("Base (1.3GB)", userData="base")
        self.unimernet_combo.addItem("Small (773MB)", userData="small")
        self.unimernet_combo.addItem("Tiny (441MB)", userData="tiny")
        self.unimernet_combo.currentIndexChanged.connect(self._on_unimernet_variant_changed)
        unimernet_layout.addWidget(self.unimernet_combo)
        self.unimernet_download_btn = PushButton(FluentIcon.DOWNLOAD, "下载模型(默认CPU)")
        self.unimernet_download_btn.setFixedHeight(30)
        self.unimernet_download_btn.clicked.connect(self._on_unimernet_download_clicked)
        unimernet_layout.addWidget(self.unimernet_download_btn)
        self.unimernet_open_btn = PushButton(FluentIcon.GLOBE, "打开下载页/目录")
        self.unimernet_open_btn.setFixedHeight(30)
        self.unimernet_open_btn.clicked.connect(self._on_unimernet_open_download_clicked)
        unimernet_layout.addWidget(self.unimernet_open_btn)
        lay.addWidget(self.unimernet_widget)
        # UniMERNet 隔离环境选择
        self.unimernet_env_widget = QWidget()
        unimernet_env_layout = QHBoxLayout(self.unimernet_env_widget)
        unimernet_env_layout.setContentsMargins(0, 0, 0, 0)
        unimernet_env_layout.setSpacing(6)
        unimernet_env_layout.addWidget(QLabel("UniMERNet 环境:"))
        self.unimernet_pyexe_input = QLineEdit()
        self.unimernet_pyexe_input.setPlaceholderText("选择隔离环境 python.exe")
        self.unimernet_pyexe_input.setFixedHeight(30)
        unimernet_env_layout.addWidget(self.unimernet_pyexe_input)
        self.unimernet_pyexe_browse = PushButton(FluentIcon.FOLDER, "浏览")
        self.unimernet_pyexe_browse.setFixedHeight(30)
        self.unimernet_pyexe_browse.clicked.connect(self._on_unimernet_pyexe_browse)
        unimernet_env_layout.addWidget(self.unimernet_pyexe_browse)
        self.unimernet_pyexe_clear = PushButton(FluentIcon.DELETE, "清除")
        self.unimernet_pyexe_clear.setFixedHeight(30)
        self.unimernet_pyexe_clear.clicked.connect(self._on_unimernet_pyexe_clear)
        unimernet_env_layout.addWidget(self.unimernet_pyexe_clear)
        self.unimernet_pyexe_create = PushButton(FluentIcon.DEVELOPER_TOOLS, "一键创建")
        self.unimernet_pyexe_create.setFixedHeight(30)
        self.unimernet_pyexe_create.clicked.connect(self._on_unimernet_pyexe_create)
        unimernet_env_layout.addWidget(self.unimernet_pyexe_create)
        lay.addWidget(self.unimernet_env_widget)
        self.unimernet_env_hint = QLabel("提示：建议使用独立虚拟环境，避免影响主依赖。")
        self.unimernet_env_hint.setStyleSheet("color: #666; font-size: 10px; padding: 2px;")
        self.unimernet_env_hint.setWordWrap(True)
        lay.addWidget(self.unimernet_env_hint)
        # UniMERNet 推理设备检测
        self.unimernet_torch_status = QLabel("UniMERNet 设备: 未检测")
        self.unimernet_torch_status.setStyleSheet("color: #666; font-size: 10px; padding: 2px;")
        self.unimernet_torch_status.setWordWrap(True)
        lay.addWidget(self.unimernet_torch_status)
        self.unimernet_torch_btn_row = QWidget()
        unimernet_torch_btn_layout = QHBoxLayout(self.unimernet_torch_btn_row)
        unimernet_torch_btn_layout.setContentsMargins(0, 0, 0, 0)
        unimernet_torch_btn_layout.setSpacing(6)
        self.unimernet_torch_install_gpu = PushButton(FluentIcon.SETTING, "安装/切换 GPU 版本")
        self.unimernet_torch_install_gpu.setFixedHeight(30)
        self.unimernet_torch_install_gpu.clicked.connect(lambda: self._install_env_torch("unimernet", "gpu"))
        unimernet_torch_btn_layout.addWidget(self.unimernet_torch_install_gpu)
        self.unimernet_torch_reinstall = PushButton(FluentIcon.SYNC, "重装")
        self.unimernet_torch_reinstall.setFixedHeight(30)
        self.unimernet_torch_reinstall.clicked.connect(lambda: self._reinstall_env_torch("unimernet"))
        unimernet_torch_btn_layout.addWidget(self.unimernet_torch_reinstall)
        self.unimernet_torch_refresh = PushButton(FluentIcon.UPDATE, "刷新检测")
        self.unimernet_torch_refresh.setFixedHeight(30)
        self.unimernet_torch_refresh.clicked.connect(lambda: self._refresh_env_status("unimernet"))
        unimernet_torch_btn_layout.addWidget(self.unimernet_torch_refresh)
        lay.addWidget(self.unimernet_torch_btn_row)
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
        self.terminal_env_combo.addItem("主环境（程序 / pix2tex）", userData="main")
        self.terminal_env_combo.addItem("pix2text 隔离环境", userData="pix2text")
        self.terminal_env_combo.addItem("UniMERNet 隔离环境", userData="unimernet")
        terminal_layout.addWidget(self.terminal_env_combo)
        self.btn_terminal = PushButton(FluentIcon.COMMAND_PROMPT, "打开环境终端")
        self.btn_terminal.setFixedHeight(36)
        self.btn_terminal.setToolTip("打开所选环境的终端，可手动安装/修复依赖。\n⚠️ 请谨慎操作，错误的命令可能损坏环境！")
        terminal_layout.addWidget(self.btn_terminal)
        lay.addWidget(terminal_row)
        # 依赖管理向导
        self.btn_deps_wizard = PushButton(FluentIcon.DEVELOPER_TOOLS, "依赖管理向导")
        self.btn_deps_wizard.setFixedHeight(36)
        self.btn_deps_wizard.setToolTip("打开依赖管理向导，可安装/升级 GPU 加速层、模型依赖等")
        lay.addWidget(self.btn_deps_wizard)
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
        mapping = {0: "main", 1: "pix2text", 2: "unimernet"}
        self._terminal_env_key = mapping.get(index, "main")
    def _get_terminal_env_key(self) -> str:
        try:
            text = self.terminal_env_combo.currentText()
        except Exception:
            text = ""
        text_lower = (text or "").lower()
        if "pix2text" in text_lower:
            return "pix2text"
        if "unimernet" in text_lower:
            return "unimernet"
        if "主环境" in text or "main" in text_lower:
            return "main"
        try:
            idx = self.terminal_env_combo.currentIndex()
        except Exception:
            idx = 0
        mapping = {0: "main", 1: "pix2text", 2: "unimernet"}
        return mapping.get(idx, "main")
    def _probe_module_installed(self, pyexe: str, module: str) -> bool:
        import subprocess
        if not pyexe or not os.path.exists(pyexe):
            return False
        code = f"import importlib.util, sys; sys.exit(0 if importlib.util.find_spec(\"{module}\") else 1)"
        try:
            try:
                res = subprocess.run([pyexe, "-c", code], capture_output=True, text=True, timeout=5)
            except subprocess.TimeoutExpired:
                fallback = self._infer_torch_info_from_env(pyexe)
                if fallback:
                    return fallback
                return {"present": False, "error": "timeout"}
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

    def _probe_torch_info(self, pyexe: str) -> dict:
        import json
        import subprocess
        if not pyexe or not os.path.exists(pyexe):
            return {"present": False, "error": "python.exe not found"}
        code = ""
        code += "import json\n"
        code += "try:\n"
        code += " import torch\n"
        code += " info = {\"present\": True, \"cuda_version\": torch.version.cuda, \"cuda_available\": torch.cuda.is_available()}\n"
        code += "except Exception as e:\n"
        code += " info = {\"present\": False, \"error\": str(e)}\n"
        code += "print(json.dumps(info))\n"
        try:
            try:
                res = subprocess.run([pyexe, "-c", code], capture_output=True, text=True, timeout=5)
            except subprocess.TimeoutExpired:
                fallback = self._infer_torch_info_from_env(pyexe)
                if fallback:
                    return fallback
                return {"present": False, "error": "timeout"}
            stdout = (res.stdout or "").strip()
            stderr = (res.stderr or "").strip()
            lines = []
            if stdout:
                lines.extend(stdout.splitlines())
            if stderr:
                lines.extend(stderr.splitlines())
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if isinstance(data, dict):
                        return data
                except Exception:
                    continue
            if stdout or stderr:
                return {"present": False, "error": (stderr or stdout)}
            fallback = self._infer_torch_info_from_env(pyexe)
            if fallback:
                return fallback
        except Exception as e:
            return {"present": False, "error": str(e)}
        return {"present": False, "error": "no output"}
    def _set_env_torch_ui(self, env_key: str, info: dict, pyexe: str):
        label = self.pix2text_torch_status if env_key == "pix2text" else self.unimernet_torch_status
        install_gpu = self.pix2text_torch_install_gpu if env_key == "pix2text" else self.unimernet_torch_install_gpu
        reinstall_btn = self.pix2text_torch_reinstall if env_key == "pix2text" else self.unimernet_torch_reinstall
        if info.get("error") == "timeout":
            label.setText(f"{env_key} 设备: 获取超时")
            install_gpu.setVisible(True)
            reinstall_btn.setVisible(True)
            return
        if not pyexe or not os.path.exists(pyexe):
            label.setText(f"{env_key} \u8bbe\u5907: \u73af\u5883\u672a\u914d\u7f6e")
            # 按钮常驻：未配置时点击会提示先选择/创建环境
            install_gpu.setVisible(True)
            reinstall_btn.setVisible(False)
            return
        if not info.get("present"):
            label.setText(f"{env_key} \u8bbe\u5907: \u672a\u5b89\u88c5 PyTorch\uff08\u9ed8\u8ba4\u5c06\u4e3a CPU \u7248\uff09")
            install_gpu.setVisible(True)
            reinstall_btn.setVisible(False)
            return
        cuda_ver = info.get("cuda_version")
        cuda_ok = info.get("cuda_available")
        if cuda_ver:
            suffix = "\uff08CUDA \u4e0d\u53ef\u7528\uff09" if cuda_ok is False else ""
            label.setText(f"{env_key} \u8bbe\u5907: GPU \u7248\u5df2\u5b89\u88c5{suffix}")
        else:
            label.setText(f"{env_key} \u8bbe\u5907: CPU \u7248\u5df2\u5b89\u88c5")
        # 按钮常驻，便于切换 GPU 版本
        install_gpu.setVisible(True)
        reinstall_btn.setVisible(True)

    def _schedule_env_torch_probe(self, env_key: str):
        if env_key not in ("pix2text", "unimernet"):
            return
        pyexe = (self.pix2text_pyexe_input.text().strip() if env_key == "pix2text" else self.unimernet_pyexe_input.text().strip())
        label = self.pix2text_torch_status if env_key == "pix2text" else self.unimernet_torch_status
        label.setText(f"{env_key} 设备: 检测中...")
        def worker():
            info = self._probe_torch_info(pyexe)
            try:
                self.env_torch_probe_done.emit(env_key, info, pyexe)
            except Exception:
                pass
        import threading
        threading.Thread(target=worker, daemon=True).start()

    def _refresh_env_status(self, env_key: str):
        if env_key not in ("pix2text", "unimernet"):
            return
        self._schedule_env_torch_probe(env_key)
        if env_key == "pix2text":
            self._schedule_pix2text_pkg_probe()
    def _detect_cuda_tag(self) -> str | None:
        import subprocess
        try:
            res = subprocess.run(["nvcc", "--version"], capture_output=True, text=True, timeout=5)
            out = (res.stdout or "") + "\n" + (res.stderr or "")
            out = out.lower()
            # sample: release 11.8, V11.8.89
            if "release 11.8" in out or "v11.8" in out:
                return "cu118"
            if "release 12.1" in out or "v12.1" in out:
                return "cu121"
            if "release 12.4" in out or "v12.4" in out:
                return "cu124"
        except Exception:
            return None
        return None
    def _install_env_torch(self, env_key: str, mode: str, include_model: bool = True):
        pyexe = self.pix2text_pyexe_input.text().strip() if env_key == "pix2text" else self.unimernet_pyexe_input.text().strip()
        if not pyexe or not os.path.exists(pyexe):
            self._show_info("环境未配置", "请先选择或创建隔离环境。", "warning")
            return
        extra_index = " --extra-index-url https://pypi.org/simple"
        if mode == "gpu":
            tag = self._detect_cuda_tag()
            if not tag:
                self._show_info("CUDA 未检测到", "未检测到 nvcc，无法自动选择 GPU 版本，请先安装 CUDA Toolkit。", "warning")
                return
            cmd = f"\"{pyexe}\" -m pip install torch==2.7.1 torchvision==0.22.1 --index-url https://download.pytorch.org/whl/{tag}{extra_index}"
        else:
            cmd = f"\"{pyexe}\" -m pip install torch==2.7.1 torchvision==0.22.1 --index-url https://download.pytorch.org/whl/cpu{extra_index}"
        model_cmd = ""
        if env_key == "pix2text":
            model_cmd = f"\"{pyexe}\" -m pip install -U pix2text"
        elif env_key == "unimernet":
            model_cmd = f"\"{pyexe}\" -m pip install -U \"unimernet[full]\""
        if include_model:
            if mode == "gpu":
                full_cmd = cmd + ("\n" + model_cmd if model_cmd else "")
            else:
                full_cmd = model_cmd or cmd
        else:
            full_cmd = cmd
        msg = (
            f"将使用隔离环境安装 {mode.upper()} 版 PyTorch：\n\n"
            f"{full_cmd}\n\n"
            "安装完成后请重新检测。"
        )
        dlg = MessageBox("安装 PyTorch", msg, self)
        dlg.yesButton.setText("复制命令并打开终端")
        dlg.cancelButton.setText("仅复制命令")
        def _do_copy(open_terminal: bool):
            try:
                pyperclip.copy(full_cmd)
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
    def _reinstall_env_torch(self, env_key: str):
        items = ["CPU", "GPU"]
        choice, ok = QInputDialog.getItem(self, "重装 PyTorch", "选择要重装的版本:", items, 0, False)
        if not ok:
            return
        mode = "gpu" if choice == "GPU" else "cpu"
        self._install_env_torch(env_key, mode, include_model=False)
    def _init_model_combo(self):
        # 初始化模型下拉框的选择状态
        current = "pix2tex"
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
        self._init_unimernet_variant()
        self._update_pix2text_visibility()
        self._update_unimernet_visibility()
    def _on_model_combo_changed(self, index: int):
        # 模型下拉框选择变化
        if index < 0 or index >= len(self._model_options):
            return
        key, _ = self._model_options[index]
        if key == "pix2text":
            if self._is_pix2text_ready():
                mode_key = self._get_pix2text_mode_key()
                self.select_model(self._pix2text_mode_to_model(mode_key))
            else:
                # 触发加载/提示，但保持 UI 选择在 pix2text
                self.select_model("pix2text")
        else:
            self.select_model(key)
        self._update_model_desc()
        self._update_pix2text_visibility()
        self._update_unimernet_visibility()
    def _get_unimernet_model_dir(self, variant: str) -> Path:
        return self._get_model_dir_base() / f"unimernet_{variant}"
    def _is_unimernet_variant_available(self, variant: str) -> bool:
        try:
            model_dir = self._get_unimernet_model_dir(variant)
            if not model_dir.exists() or not model_dir.is_dir():
                return False
            weight_files = [
                model_dir / "pytorch_model.pth",
                model_dir / f"unimernet_{variant}.pth",
                model_dir / "pytorch_model.bin",
                model_dir / "model.safetensors",
            ]
            if any(p.exists() for p in weight_files):
                return True
            # fallback: any .pth weights in folder
            return any(model_dir.glob("*.pth"))
        except Exception:
            return False
    def _refresh_unimernet_variants(self):
        labels = {
            "base": "Base (1.3GB)",
            "small": "Small (773MB)",
            "tiny": "Tiny (441MB)",
        }
        for i in range(self.unimernet_combo.count()):
            variant = self.unimernet_combo.itemData(i)
            available = self._is_unimernet_variant_available(variant)
            label = labels.get(variant, str(variant))
            suffix = "（已下载）" if available else "（未下载）"
            self.unimernet_combo.setItemText(i, f"{label}{suffix}")
    def _init_unimernet_variant(self):
        self._refresh_unimernet_variants()
        current = "base"
        if self.parent() and hasattr(self.parent(), "cfg"):
            current = self.parent().cfg.get("unimernet_variant", "base")
        for i in range(self.unimernet_combo.count()):
            if self.unimernet_combo.itemData(i) == current:
                self.unimernet_combo.setCurrentIndex(i)
                break
        self._init_unimernet_pyexe()
        self._schedule_env_torch_probe("unimernet")
    def _on_unimernet_variant_changed(self, index: int):
        if index < 0:
            return
        variant = self.unimernet_combo.itemData(index)
        if self.parent() and hasattr(self.parent(), "cfg"):
            self.parent().cfg.set("unimernet_variant", variant)
        if self.parent() and hasattr(self.parent(), "model") and self.parent().model:
            try:
                self.parent().model._unimernet_subprocess_ready = False
                self.parent().model._unimernet_import_failed = False
            except Exception:
                pass
        if self.parent() and hasattr(self.parent(), "_apply_unimernet_env"):
            try:
                self.parent()._apply_unimernet_env()
            except Exception:
                pass
        if self.parent() and hasattr(self.parent(), "refresh_status_label"):
            try:
                self.parent().refresh_status_label()
            except Exception:
                pass
    def _on_unimernet_download_clicked(self):
        if self.parent() and hasattr(self.parent(), "_show_unimernet_setup_tip"):
            try:
                self.parent()._show_unimernet_setup_tip()
            except Exception:
                pass
    def _on_unimernet_open_download_clicked(self):
        if self.parent() and hasattr(self.parent(), "_open_unimernet_download_page"):
            try:
                self.parent()._open_unimernet_download_page()
            except Exception:
                pass
    def _on_pix2text_download_clicked(self):
        if self.parent() and hasattr(self.parent(), "_show_pix2text_setup_tip"):
            try:
                self.parent()._show_pix2text_setup_tip()
            except Exception:
                pass
    def _on_pix2text_open_download_clicked(self):
        if self.parent() and hasattr(self.parent(), "_open_pix2text_download_page"):
            try:
                self.parent()._open_pix2text_download_page()
            except Exception:
                pass
    def _init_pix2text_pyexe(self):
        if not self.parent() or not hasattr(self.parent(), "cfg"):
            return
        val = self.parent().cfg.get("pix2text_pyexe", "")
        if val:
            self.pix2text_pyexe_input.setText(val)
    def _init_pix2text_mode(self):
        mode = "formula"
        if self.parent() and hasattr(self.parent(), "cfg"):
            mode = self.parent().cfg.get("pix2text_mode", "formula")
        for i in range(self.pix2text_mode_combo.count()):
            if self.pix2text_mode_combo.itemData(i) == mode:
                self.pix2text_mode_combo.setCurrentIndex(i)
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
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 pix2text 环境 Python",
            "",
            "python.exe (python.exe);;所有文件 (*.*)"
        )
        if not path:
            return
        self.pix2text_pyexe_input.setText(path)
        if self.parent() and hasattr(self.parent(), "cfg"):
            self.parent().cfg.set("pix2text_pyexe", path)
        if self.parent() and hasattr(self.parent(), "_apply_pix2text_env"):
            try:
                self.parent()._apply_pix2text_env()
            except Exception:
                pass
        self._schedule_env_torch_probe("pix2text")
        self._schedule_pix2text_pkg_probe()
    def _on_pix2text_pyexe_clear(self):
        self.pix2text_pyexe_input.clear()
        if self.parent() and hasattr(self.parent(), "cfg"):
            self.parent().cfg.set("pix2text_pyexe", "")
        if self.parent() and hasattr(self.parent(), "_apply_pix2text_env"):
            try:
                self.parent()._apply_pix2text_env()
            except Exception:
                pass
        self._schedule_env_torch_probe("pix2text")
        self._schedule_pix2text_pkg_probe()
    def _get_model_dir_base(self) -> Path:
        parent = self.parent()
        if parent is not None and hasattr(parent, "model_dir"):
            try:
                return Path(getattr(parent, "model_dir"))
            except Exception:
                pass
        env = os.environ.get("LATEXSNIPPER_MODEL_DIR", "")
        if env:
            return Path(env)
        return Path.cwd() / "models"
    def _on_pix2text_pyexe_create(self):
        """一键创建 pix2text 隔离环境。"""
        base_py = os.environ.get("LATEXSNIPPER_PYEXE", sys.executable)
        if not base_py or not os.path.exists(base_py):
            base_py = sys.executable
        env_dir = self._get_model_dir_base() / "pix2text_env"
        py_path = env_dir / "Scripts" / "python.exe"
        if py_path.exists():
            self.pix2text_pyexe_input.setText(str(py_path))
            if self.parent() and hasattr(self.parent(), "cfg"):
                self.parent().cfg.set("pix2text_pyexe", str(py_path))
            if self.parent() and hasattr(self.parent(), "_apply_pix2text_env"):
                try:
                    self.parent()._apply_pix2text_env()
                except Exception:
                    pass
            try:
                InfoBar.info(
                    title="环境已存在",
                    content=f"已使用现有隔离环境：{py_path}",
                    parent=self,
                    duration=3000,
                    position=InfoBarPosition.TOP
                )
            except Exception:
                pass
            return
        try:
            env_dir.mkdir(parents=True, exist_ok=True)
            r = subprocess.run(
                [base_py, "-m", "venv", str(env_dir)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120
            )
            if r.returncode != 0:
                raise RuntimeError(r.stderr or r.stdout or "venv failed")
        except Exception as e:
            custom_warning_dialog("错误", f"创建隔离环境失败: {e}", self)
            return
        if not py_path.exists():
            custom_warning_dialog("错误", "隔离环境创建完成但未找到 python.exe", self)
            return
        self.pix2text_pyexe_input.setText(str(py_path))
        if self.parent() and hasattr(self.parent(), "cfg"):
            self.parent().cfg.set("pix2text_pyexe", str(py_path))
        if self.parent() and hasattr(self.parent(), "_apply_pix2text_env"):
            try:
                self.parent()._apply_pix2text_env()
            except Exception:
                pass
        try:
            InfoBar.success(
                title="隔离环境创建完成",
                content=f"已创建并切换到：{py_path}",
                parent=self,
                duration=3000,
                position=InfoBarPosition.TOP
            )
        except Exception:
            pass
        self._schedule_env_torch_probe("pix2text")
        self._schedule_pix2text_pkg_probe()
    def _init_unimernet_pyexe(self):
        if not self.parent() or not hasattr(self.parent(), "cfg"):
            return
        val = self.parent().cfg.get("unimernet_pyexe", "")
        if val:
            self.unimernet_pyexe_input.setText(val)
    def _on_unimernet_pyexe_browse(self):
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 UniMERNet 环境 Python",
            "",
            "python.exe (python.exe);;所有文件 (*.*)"
        )
        if not path:
            return
        self.unimernet_pyexe_input.setText(path)
        if self.parent() and hasattr(self.parent(), "cfg"):
            self.parent().cfg.set("unimernet_pyexe", path)
        if self.parent() and hasattr(self.parent(), "_apply_unimernet_env"):
            try:
                self.parent()._apply_unimernet_env()
            except Exception:
                pass
        self._schedule_env_torch_probe("unimernet")
    def _on_unimernet_pyexe_clear(self):
        self.unimernet_pyexe_input.clear()
        if self.parent() and hasattr(self.parent(), "cfg"):
            self.parent().cfg.set("unimernet_pyexe", "")
        if self.parent() and hasattr(self.parent(), "_apply_unimernet_env"):
            try:
                self.parent()._apply_unimernet_env()
            except Exception:
                pass
        self._schedule_env_torch_probe("unimernet")
    def _on_unimernet_pyexe_create(self):
        """一键创建 UniMERNet 隔离环境。"""
        base_py = os.environ.get("LATEXSNIPPER_PYEXE", sys.executable)
        if not base_py or not os.path.exists(base_py):
            base_py = sys.executable
        env_dir = self._get_model_dir_base() / "unimernet_env"
        py_path = env_dir / "Scripts" / "python.exe"
        if py_path.exists():
            self.unimernet_pyexe_input.setText(str(py_path))
            if self.parent() and hasattr(self.parent(), "cfg"):
                self.parent().cfg.set("unimernet_pyexe", str(py_path))
            if self.parent() and hasattr(self.parent(), "_apply_unimernet_env"):
                try:
                    self.parent()._apply_unimernet_env()
                except Exception:
                    pass
            try:
                InfoBar.info(
                    title="环境已存在",
                    content=f"已使用现有隔离环境：{py_path}",
                    parent=self,
                    duration=3000,
                    position=InfoBarPosition.TOP
                )
            except Exception:
                pass
            return
        try:
            env_dir.mkdir(parents=True, exist_ok=True)
            r = subprocess.run(
                [base_py, "-m", "venv", str(env_dir)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120
            )
            if r.returncode != 0:
                raise RuntimeError(r.stderr or r.stdout or "venv failed")
        except Exception as e:
            custom_warning_dialog("错误", f"创建隔离环境失败: {e}", self)
            return
        if not py_path.exists():
            custom_warning_dialog("错误", "隔离环境创建完成但未找到 python.exe", self)
            return
        self.unimernet_pyexe_input.setText(str(py_path))
        if self.parent() and hasattr(self.parent(), "cfg"):
            self.parent().cfg.set("unimernet_pyexe", str(py_path))
        if self.parent() and hasattr(self.parent(), "_apply_unimernet_env"):
            try:
                self.parent()._apply_unimernet_env()
            except Exception:
                pass
        try:
            InfoBar.success(
                title="隔离环境创建完成",
                content=f"已创建并切换到：{py_path}",
                parent=self,
                duration=3000,
                position=InfoBarPosition.TOP
            )
        except Exception:
            pass
        self._schedule_env_torch_probe("unimernet")
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
            self.pix2text_torch_btn_row.setVisible(visible)
            try:
                self.pix2text_dl_widget.setVisible(visible)
            except Exception:
                pass
            # 识别类型始终可见（便于用户预先选择）
            self.pix2text_mode_widget.setVisible(visible)
            if visible:
                if not pyexe_exists:
                    self.pix2text_env_hint.setText("⚠️ pix2text 未配置：请先选择或创建隔离环境。")
                elif not ready:
                    self.pix2text_env_hint.setText("⚠️ pix2text 未部署：请先下载模型（并安装 CPU/GPU 版 PyTorch）。")
                else:
                    self.pix2text_env_hint.setText("💡 pix2text 已部署，可选择识别类型。")
        except Exception:
            pass
    def _update_unimernet_visibility(self):
        key = None
        idx = self.model_combo.currentIndex()
        if idx >= 0 and idx < len(self._model_options):
            key, _ = self._model_options[idx]
        visible = (key == "unimernet")
        try:
            if visible:
                self._refresh_unimernet_variants()
            self.unimernet_widget.setVisible(visible)
            self.unimernet_env_widget.setVisible(visible)
            self.unimernet_env_hint.setVisible(visible)
            self.unimernet_torch_status.setVisible(visible)
            self.unimernet_torch_btn_row.setVisible(visible)
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
            "pix2tex": "轻量公式识别，速度快，适合简单公式。",
            "pix2text": "高精度公式识别，适合复杂公式（需单独配置 pix2text 环境）。",
            "unimernet": "UniMERNet 强化公式识别（实验），需单独安装模型与依赖。",
        }
        desc = descriptions.get(key, "")
        if key == "pix2text":
            desc += "\n提示：部署完成后可选择识别类型（公式/混合/文字/整页/表格）。"
        elif key == "unimernet":
            desc += "\n提示：请在设置中下载模型并配置隔离环境。"
        self.lbl_model_desc.setText(desc)
    def _open_terminal(self, env_key: str | None = None):
        if isinstance(env_key, bool):
            env_key = None
        import subprocess
        import os
        from qfluentwidgets import MessageBox, InfoBar, InfoBarPosition
        if env_key is None:
            env_key = self._get_terminal_env_key()
        if env_key not in ("main", "pix2text", "unimernet"):
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
            if key == "pix2text" and cfg:
                return cfg.get("pix2text_pyexe", "")
            if key == "unimernet" and cfg:
                return cfg.get("unimernet_pyexe", "")
            return os.environ.get("LATEXSNIPPER_PYEXE", sys.executable)
        pyexe = _get_pyexe(env_key)
        # auto-detect default env path under models if not configured
        def _auto_detect_env_path(key: str) -> str:
            if key not in ("pix2text", "unimernet"):
                return ""
            try:
                base = self._get_model_dir_base()
                py_path = base / f"{key}_env" / "Scripts" / "python.exe"
                return str(py_path) if py_path.exists() else ""
            except Exception:
                return ""
        if (not pyexe or not os.path.exists(pyexe)) and env_key in ("pix2text", "unimernet"):
            auto_path = _auto_detect_env_path(env_key)
            if auto_path:
                pyexe = auto_path
                if cfg:
                    if env_key == "pix2text":
                        cfg.set("pix2text_pyexe", auto_path)
                    else:
                        cfg.set("unimernet_pyexe", auto_path)
                try:
                    if env_key == "pix2text":
                        self.pix2text_pyexe_input.setText(auto_path)
                    else:
                        self.unimernet_pyexe_input.setText(auto_path)
                except Exception:
                    pass
        print(f"[DEBUG] Terminal pyexe initial: {pyexe}")
        if not pyexe or not os.path.exists(pyexe):
            if env_key != "main":
                InfoBar.warning(
                    title="环境未部署",
                    content="未找到所选环境的 python.exe，请先部署或配置该环境。",
                    parent=self,
                    duration=4000,
                    position=InfoBarPosition.TOP
                )
                return
            # main env fallback
            pyexe = _get_pyexe("main")
            if not pyexe or not os.path.exists(pyexe):
                pyexe = sys.executable
        pyexe_dir = os.path.dirname(pyexe)
        scripts_dir = os.path.join(pyexe_dir, "Scripts")
        venv_dir = pyexe_dir
        env_name = {
            "main": "主环境",
            "pix2text": "pix2text 隔离环境",
            "unimernet": "UniMERNet 隔离环境",
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
        env_desc = {
            "main": "主环境（程序 / pix2tex / 核心依赖）",
            "pix2text": "pix2text 独立环境",
            "unimernet": "UniMERNet 独立环境",
        }.get(env_key, "主环境（程序 / pix2tex / 核心依赖）")
        help_lines = [
            "echo.",
            "echo ================================================================================",
            f"echo                        LaTeXSnipper 环境终端 - {env_name}",
            "echo ================================================================================",
            "echo.",
            f"echo [*] 环境: {env_desc}",
            f"echo [*] Python: {pyexe_dir}",
            "echo [*] pip/python 将使用此环境",
            "echo.",
            "echo [隔离策略]",
            "echo   - 主环境: 程序 + pix2tex + 基础/核心依赖",
            "echo   - pix2text / UniMERNet: 独立隔离环境",
            "echo.",
            "echo [版本修复 - 常见冲突]",
            "echo   pip install numpy==1.26.4",
            "echo   pip install protobuf==4.25.8",
            "echo   pip install pydantic==2.9.2 pydantic-core==2.23.4",
            "echo.",
            "echo [PyTorch GPU]",
            "echo   nvcc --version",
            "echo   pip install torch==2.7.1 torchvision==0.22.1 --index-url https://download.pytorch.org/whl/cu118",
            "echo.",
            "echo [ONNX Runtime]",
            "echo   pip install onnxruntime-gpu==1.18.1",
            "echo   pip install onnxruntime==1.18.1",
            "echo.",
        ]
        if env_key == "main":
            help_lines += [
                "echo [模型]",
                "echo   pip install pix2tex==0.1.4",
                "echo.",
            ]
        elif env_key == "pix2text":
            help_lines += [
                "echo [依赖]",
                "echo   pip install -U torch==2.7.1 torchvision==0.22.1 onnxruntime==1.22.1 optimum==2.0.0 torchmetrics==1.7.4 pymupdf==1.26.7",
                "echo.",
                "echo [模型]",
                "echo   pip install -U pix2text==1.1.4",
                "echo   python -c \"from pix2text import Pix2Text; Pix2Text()\"",
                "echo.",
            ]
        else:
            help_lines += [
                "echo [模型]",
                "echo   pip install -U \"unimernet[full]\"",
                "echo   git lfs install",
                "echo   # 使用设置里的下载按钮或手动下载权重",
                "echo.",
            ]
        help_lines += [
            "echo [诊断]",
            "echo   pip list",
            "echo   pip check",
            "echo   python -c \"import torch; print(\"CUDA:\", torch.cuda.is_available(), \"Ver:\", torch.version.cuda)\"",
            "echo   nvidia-smi",
            "echo   nvcc --version",
            "echo.",
            "echo [清理缓存]",
            "echo   pip cache purge",
            "echo.",
            "echo ================================================================================",
            "echo.",
        ]
        help_str = " && ".join(help_lines)
        try:
            if as_admin:
                import tempfile
                batch_content = "@echo off\n" \
                    + "chcp 65001 >nul\n" \
                    + f'cd /d "{venv_dir}"\n' \
                    + f'set "PATH={pyexe_dir};{scripts_dir};%PATH%"\n' \
                    + help_str.replace("echo", "echo") + "\n" \
                    + "cmd /k\n"
                with tempfile.NamedTemporaryFile(mode="w", suffix=".bat", delete=False, encoding="utf-8") as f:
                    f.write(batch_content)
                    batch_path = f.name
                import ctypes
                ctypes.windll.shell32.ShellExecuteW(
                    None, "runas", "cmd.exe", f"/c \"{batch_path}\"", None, 1
                )
                self._show_info("终端已打开", "已弹出 UAC 授权提示。", "success")
            else:
                import tempfile
                batch_content_normal = "@echo off\n" \
                    + "chcp 65001 >nul\n" \
                    + f'cd /d "{venv_dir}"\n' \
                    + f'set "PATH={pyexe_dir};{scripts_dir};%PATH%"\n' \
                    + help_str.replace("echo", "echo") + "\n" \
                    + "cmd /k\n"
                with tempfile.NamedTemporaryFile(mode="w", suffix=".bat", delete=False, encoding="utf-8") as f:
                    f.write(batch_content_normal)
                    batch_path = f.name
                subprocess.Popen(["cmd.exe", "/c", "start", "", "cmd.exe", "/k", batch_path], cwd=venv_dir)
                self._show_info("终端已打开", "已以普通模式打开。", "success")
        except Exception as e:
            self._show_info("终端打开失败", str(e), "error")
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
        try:
            # 启动新进程
            if script_path.endswith('.py'):
                subprocess.Popen(
                    [python_exe, script_path, "--force-deps-check"],
                    env=env,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                )
            else:
                # 打包后的 exe
                subprocess.Popen(
                    [script_path, "--force-deps-check"],
                    env=env,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                )
            # 关闭当前程序
            from PyQt6.QtWidgets import QApplication
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
        current = None
        desired = None
        if self.parent() and hasattr(self.parent(), "desired_model"):
            desired = self.parent().desired_model
        elif self.parent() and hasattr(self.parent(), "cfg"):
            desired = self.parent().cfg.get("desired_model", None)
        if self.parent() and hasattr(self.parent(), "current_model"):
            current = self.parent().current_model
        target = desired or current
        if target and str(target).startswith("pix2text"):
            target_key = "pix2text"
        else:
            target_key = target
        if target_key:
            for i, (key, _) in enumerate(self._model_options):
                if key == target_key:
                    self.model_combo.blockSignals(True)
                    self.model_combo.setCurrentIndex(i)
                    self.model_combo.blockSignals(False)
                    break
        self._init_pix2text_mode()
        self._update_model_desc()
        self._update_pix2text_visibility()
        self._update_unimernet_visibility()
# ---------------- 主窗口 ----------------
from PyQt6.QtCore import Qt
