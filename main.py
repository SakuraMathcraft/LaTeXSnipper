import os
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"   # 强制 CPU 模式
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "max_split_size_mb:128" # 避免显存碎片化
os.environ["ORT_DISABLE_OPENCL"] = "1"  # 避免 OpenCL 相关错误
os.environ.setdefault("NO_ALBUMENTATIONS_UPDATE", "1")  # 避免 albumentations 检查更新
os.environ.setdefault("ORT_DISABLE_AZURE", "1") # 避免 Azure 相关错误
import faulthandler; faulthandler.enable()
from PyQt6.QtCore import QTimer
import sys
import json
from io import BytesIO
from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import (QVBoxLayout, QListWidget, QMenu, QInputDialog, QPushButton,
                             QMessageBox, QFileDialog)
from PyQt6.QtCore import Qt, QObject, QThread, QCoreApplication
from PyQt6.QtGui import QIcon, QKeySequence, QShortcut
import pyperclip
from PIL import Image

# 绝对导入（依赖 backend/__init__.py 与 backend/qhotkey/__init__.py）
from backend.qhotkey import QHotkey, GlobalHotkey
from updater import check_update_dialog

from PyQt6.QtWidgets import (QApplication, QWidget, QLabel, QSystemTrayIcon,
                             QDialog, QTextEdit, QHBoxLayout, QScrollArea, QSplitter)
from PyQt6.QtCore import QBuffer, QIODevice, QPropertyAnimation, QEasingCurve, pyqtSignal

from backend.capture_overlay import ScreenCaptureOverlay
from backend.model import ModelWrapper
flags = [
    "--use-angle=d3d11",
    "--ignore-gpu-blocklist",
    "--enable-logging=stderr",
    "--v=1",
]
ACTION_BTN_STYLE = (
    "QPushButton{background:#3daee9;color:#fff;border-radius:4px;"
    "padding:4px 10px;font-size:12px;}"
    "QPushButton:hover{background:#5dbff2;}"
)
# ---------------- 获取 PyInstaller 打包路径 ----------------
if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS
else:
    base_path = os.path.dirname(__file__)

rapidocr_path = os.path.join(base_path, "rapidocr")
sys.path.append(rapidocr_path)
from rapidocr import main as rapidocr_main
_ = rapidocr_main
# 样式常量
HOVER_STYLE_BASE = "QWidget{background:#fefefe;border:1px solid #cfcfcf;border-radius:5px;padding:6px;}"
HOVER_STYLE_ACTIVE = "QWidget{background:#ffffff;border:1px solid #999;border-radius:5px;padding:6px;}"
BTN_PRIMARY = ("QPushButton{background:#3daee9;color:#fff;border-radius:4px;padding:6px;}"
               "QPushButton:hover{background:#5dbff2;}")
MAX_HISTORY = 200
ENABLE_ROW_ANIMATION = False    # 历史记录行动画开关
SAFE_MINIMAL = True          # 第一步：最小化测试开关
DISABLE_GLOBAL_HOTKEY = False # 若为 True 不注册全局热键
DISABLE_WEBENGINE_PREVIEW = False
CONFIG_FILENAME = "LaTeXSnipper_config.json"
DEFAULT_FAVORITES_NAME = "favorites.json"
DEFAULT_HISTORY_NAME = "history.json"
from typing import TYPE_CHECKING
if not DISABLE_WEBENGINE_PREVIEW:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
else:
    QWebEngineView = None  # 占位
def resource_path(relative: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
    return os.path.join(base, relative)

class ConfigManager:
    def __init__(self):
        self.path = os.path.join(os.path.expanduser("~"), CONFIG_FILENAME)
        self.data = {}
        self.load()

    def load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
                if not isinstance(self.data, dict):
                    self.data = {}
            except Exception:
                self.data = {}
        else:
            self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print("[Config] 保存失败:", e)

# ---------------- MathJax HTML 模板 ----------------
MATHJAX_HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<script>
window.MathJax = {
  tex: {
    inlineMath: [['$','$'], ['\\(','\\)']]
  }
};
</script>
<script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
<style>
body { font-family: sans-serif; padding:5px; margin:0; background:#f0f0f0; }
</style>
</head>
<body>
$$__LATEX__$$
</body>
</html>
"""

def build_math_html(latex: str) -> str:
    return MATHJAX_HTML_TEMPLATE.replace("__LATEX__", (latex or "").strip())

def load_math_into(view, latex: str):
    if not view:
        return
    view.setHtml("<html><body style='background:#f0f0f0;color:#666;font-size:12px;'>加载中...</body></html>")
    html = build_math_html(latex or "")
    QTimer.singleShot(0, lambda: view.setHtml(html))
# ---------------- Hover 动画控件 ----------------
class HoverWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.base_style = HOVER_STYLE_BASE
        self.hover_style = HOVER_STYLE_ACTIVE
        self.setStyleSheet(self.base_style)

    def enterEvent(self, event):
        self.setStyleSheet(self.hover_style)
        return super().enterEvent(event)

    def leaveEvent(self, event):
        self.setStyleSheet(self.base_style)
        return super().leaveEvent(event)
class FavoritesWindow(QWidget):
    def __init__(self, cfg: ConfigManager, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setWindowTitle("公式收藏夹")
        self.setMinimumSize(400, 400)

        icon_path = resource_path("assets/icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.layout = QVBoxLayout(self)
        btn_save_path = QPushButton("选择保存路径")
        btn_save_path.setStyleSheet(BTN_PRIMARY)
        btn_save_path.clicked.connect(self.select_file)
        self.layout.addWidget(btn_save_path)

        self.list_widget = QListWidget()
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self.show_context_menu)
        self.layout.addWidget(self.list_widget)

        self.render_area = QScrollArea()
        self.render_area.setWidgetResizable(True)
        self.render_container = QWidget()
        self.render_layout = QVBoxLayout(self.render_container)
        self.render_layout.setContentsMargins(6, 6, 6, 6)
        self.render_area.setWidget(self.render_container)
        self.layout.addWidget(self.render_area)

        close_btn = QPushButton("关闭窗口")
        close_btn.setStyleSheet(BTN_PRIMARY)
        close_btn.clicked.connect(self.close)
        self.layout.addWidget(close_btn)

        self.favorites = []
        favorites_path = self.cfg.get("favorites_path")
        if not favorites_path:
            favorites_path = os.path.join(os.path.expanduser("~"), DEFAULT_FAVORITES_NAME)
            self.cfg.set("favorites_path", favorites_path)
        self.file_path = favorites_path
        self.load_favorites()
        self.preview_view = None
    def _set_status(self, msg: str):
        p = self.parent()
        if p and hasattr(p, "set_action_status"):
            p.set_action_status(msg)
    def add_favorite(self, text):
        t = (text or "").strip()
        if not t:
            self._set_status("空内容忽略")
            return
        if t in self.favorites:
            self._set_status("收藏夹里已存在该公式，忽略")
            self.show(); self.raise_(); self.activateWindow()
            return
        self.favorites.append(t)
        self.refresh_list()
        self.save_favorites()
        self.show(); self.raise_(); self.activateWindow()
        self._set_status("已加入收藏")
    def show_context_menu(self, pos):
        item = self.list_widget.itemAt(pos)
        if not item:
            return
        menu = QMenu()
        a_del = menu.addAction("删除")
        a_edit = menu.addAction("编辑")
        a_prev = menu.addAction("渲染预览")
        act = menu.exec(self.list_widget.mapToGlobal(pos))
        if act == a_del:
            try:
                self.favorites.remove(item.text())
            except ValueError:
                return
            self.refresh_list()
            self.save_favorites()
            self._set_status("已删除收藏")
        elif act == a_edit:
            new_text, ok = QInputDialog.getText(self, "编辑公式", "修改：", text=item.text())
            if ok and new_text.strip():
                idx = self.favorites.index(item.text())
                self.favorites[idx] = new_text.strip()
                self.refresh_list()
                self.save_favorites()
                self._set_status("已修改收藏")
        elif act == a_prev:
            self.render_favorite(item.text())
            self._set_status("已渲染预览")
    def refresh_list(self):
        self.list_widget.clear()
        self.list_widget.addItems(self.favorites)

    def select_file(self):
        path, _ = QFileDialog.getSaveFileName(self, "选择收藏夹保存路径", os.getcwd(), "JSON Files (*.json)")
        if path:
            self.file_path = path
            self.cfg.set("favorites_path", path)
            self.save_favorites()
            QMessageBox.information(self, "提示", f"已设置收藏保存路径: {path}")

    # ===== 5. FavoritesWindow.load_favorites 修正占位（只替换该方法）=====
    def load_favorites(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    self.favorites = [str(x) for x in data if isinstance(x, (str, int, float))]
                else:
                    self.favorites = []
            except Exception as e:
                print("加载收藏失败:", e)
                self.favorites = []
        self.refresh_list()

    def save_favorites(self):
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.favorites, f, ensure_ascii=False, indent=2)
        except Exception as e:
            QMessageBox.warning(self, "错误", f"收藏保存失败: {e}")


# ---- 5. 修改 FavoritesWindow.render_favorite ----
    def render_favorite(self, latex_code: str):
        code = (latex_code or "").strip()
        if not code:
            return
        if DISABLE_WEBENGINE_PREVIEW or self.cfg.get("disable_webengine_preview"):
            QMessageBox.information(self, "预览(降级)", code)
            return
        if self.preview_view is None:
            try:
                from PyQt6.QtWebEngineWidgets import QWebEngineView
                self.preview_view = QWebEngineView(self.render_container)
                self.preview_view.setFixedHeight(160)
                self.render_layout.addWidget(self.preview_view)
            except Exception as e:
                QMessageBox.warning(self, "错误", f"创建预览失败: {e}")
                return
        try:
            self.preview_view.setHtml(
                "<html><body style='background:#f0f0f0;font-size:12px;color:#666;'>加载中...</body></html>")
            html = build_math_html(code)
            QTimer.singleShot(0, lambda: self.preview_view.setHtml(html))
        except Exception as e:
            QMessageBox.warning(self, "错误", f"渲染失败: {e}")
# ---------------- 设置窗口 ----------------
class SettingsWindow(QDialog):
    model_changed = pyqtSignal(str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setWindowTitle("设置")
        self.resize(300, 180)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("选择公式识别模型:"))
        self.btn_pix2tex = QPushButton("pix2tex")
        self.btn_pix2text = QPushButton("pix2text")
        for b in (self.btn_pix2tex, self.btn_pix2text):
            b.setStyleSheet(BTN_PRIMARY)
        lay.addWidget(self.btn_pix2tex)
        lay.addWidget(self.btn_pix2text)
        lay.addWidget(QLabel("检查更新:"))
        self.btn_update = QPushButton("检查更新")
        self.btn_update.setStyleSheet(BTN_PRIMARY)
        lay.addWidget(self.btn_update)

        self.btn_pix2tex.clicked.connect(lambda: self.select_model("pix2tex"))
        self.btn_pix2text.clicked.connect(lambda: self.select_model("pix2text"))
        self.btn_update.clicked.connect(lambda: check_update_dialog(self))
        self.update_model_buttons()

    def update_model_buttons(self):
        cur = self.parent().current_model if self.parent() else "pix2tex"
        normal = BTN_PRIMARY
        active = ("QPushButton{background:#5dbff2;color:#fff;border-radius:4px;padding:6px;}"
                  "QPushButton:hover{background:#58c8ff;}")
        self.btn_pix2tex.setStyleSheet(active if cur == "pix2tex" else normal)
        self.btn_pix2text.setStyleSheet(active if cur == "pix2text" else normal)

    def select_model(self, model_name: str):
        if self.parent():
            self.parent().cfg.set("default_model", model_name)
        self.model_changed.emit(model_name)
        QMessageBox.information(self, "提示", f"已选择模型: {model_name}")
        self.update_model_buttons()
    def check_update(self):
        check_update_dialog(self)

# ---------------- 主窗口 ----------------
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LaTeXSnipper")
        self.setMinimumSize(520, 420)
        self._force_exit = False
        # 状态字段
        self.model_status = "未加载"
        self.action_status = ""
        self._predict_busy = False
        self.overlay = None
        self.predict_thread = None
        self.predict_worker = None
        self.settings_window = None

        # 配置与模型
        self.cfg = ConfigManager()
        self.current_model = self.cfg.get("default_model", "pix2tex")

        icon_path = resource_path("assets/icon.ico")
        self.icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()
        self.setWindowIcon(self.icon)

        try:
            self.model = ModelWrapper()
            self.model.status_signal.connect(self.show_status_message)
        except Exception as e:
            QMessageBox.warning(self, "错误", f"模型初始化失败: {e}")
            self.model = None

        # 历史
        self.history_path = os.path.join(os.path.expanduser("~"), DEFAULT_HISTORY_NAME)
        self.history = []

        # 状态栏（注意不要与方法同名）
        self.status_label = QLabel()
        self.status_label.setStyleSheet("color:#333;font-size:12px;padding:4px;")

        # 收藏窗口（需在 status_label 之后创建，便于回调写入状态）
        self.favorites_window = FavoritesWindow(self.cfg, self)

        if DISABLE_GLOBAL_HOTKEY:
            self.hotkey = None
            self._fallback_shortcut = QShortcut("Ctrl+F", self)
            self._fallback_shortcut.activated.connect(self.start_capture)
        else:
            self.hotkey = QHotkey(parent=self)
            seq = self.cfg.get("hotkey", "Ctrl+F")
            if not (seq.startswith("Ctrl+") and len(seq) == 6):
                seq = "Ctrl+F"
            self._fallback_shortcut = None
            self.hotkey.activated.connect(self.on_hotkey_triggered)
            QTimer.singleShot(0, lambda: self.register_hotkey(seq))

        # 按钮
        self.capture_button = QPushButton("截图识别")
        self.capture_button.setStyleSheet(
            "QPushButton{background:#3daee9;color:#fff;font-size:16px;padding:10px;border-radius:5px;}"
            "QPushButton:hover{background:#5dbff2;}"
        )
        self.capture_button.clicked.connect(self.start_capture)

        self.history_scroll = QScrollArea()
        self.history_scroll.setWidgetResizable(True)
        self.history_container = QWidget()
        self.history_layout = QVBoxLayout(self.history_container)
        self.history_layout.setContentsMargins(0, 0, 0, 0)
        self.history_layout.setSpacing(6)
        self.history_layout.addStretch()
        self.history_scroll.setWidget(self.history_container)

        self.clear_history_button = QPushButton("清空历史记录")
        self.change_key_button = QPushButton("设置快捷键")
        self.show_fav_button = QPushButton("打开收藏夹")
        self.settings_button = QPushButton("设置")
        for b in (self.clear_history_button, self.change_key_button, self.show_fav_button, self.settings_button):
            b.setStyleSheet(BTN_PRIMARY)

        self.clear_history_button.clicked.connect(self.clear_history)
        self.change_key_button.clicked.connect(self.set_shortcut)
        self.show_fav_button.clicked.connect(self.open_favorites)
        self.settings_button.clicked.connect(self.open_settings)

        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.capture_button)
        lbl = QLabel("历史记录")
        lbl.setStyleSheet("font-size:14px;font-weight:600;color:#333;")
        main_layout.addWidget(lbl)
        main_layout.addWidget(self.history_scroll)
        main_layout.addWidget(self.clear_history_button)
        main_layout.addWidget(self.change_key_button)
        main_layout.addWidget(self.show_fav_button)
        main_layout.addWidget(self.settings_button)
        main_layout.addWidget(self.status_label)

        # 托盘
        self.tray_icon = QSystemTrayIcon(self.icon, self)
        tray_menu = QMenu()
        tray_menu.addAction("打开主窗口", self.show_window)
        tray_menu.addAction("截图识别", self.start_capture)
        tray_menu.addAction("退出", self.truly_exit)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

        # 初始化界面
        self.load_history()
        self.update_history_ui()
        self.refresh_status_label()

        QApplication.instance().aboutToQuit.connect(self._graceful_shutdown)

    def _safe_call(self, name, fn):
        print(f"[SlotEnter] {name}")
        try:
            fn()
            print(f"[SlotExit] {name}")
        except Exception as e:
            print(f"[SlotError] {name}: {e}")
    def _defer(self, fn):
        QTimer.singleShot(0, fn)
    # ---------- 状态管理 ----------
    def refresh_status_label(self):
        base = f"当前模型: {self.current_model} | 状态: {self.model_status}"
        if self.action_status:
            base += f" | {self.action_status}"
        self.status_label.setText(base)

    def _qpixmap_to_pil(self, pixmap):
        buf = QBuffer()
        if not buf.open(QIODevice.OpenModeFlag.ReadWrite):
            raise RuntimeError("QBuffer 打开失败")
        if not pixmap.save(buf, "PNG"):
            raise RuntimeError("QPixmap 保存失败")
        data = bytes(buf.data())
        buf.close()
        return Image.open(BytesIO(data)).convert("RGB")

    def set_model_status(self, msg: str):
        self.model_status = msg
        self.refresh_status_label()

    def set_action_status(self, msg: str, auto_clear_ms: int = 2500):
        self.action_status = msg
        self.refresh_status_label()
        from PyQt6.QtCore import QTimer
        if auto_clear_ms > 0:
            QTimer.singleShot(auto_clear_ms, lambda: self._clear_action_status(msg))

    def _clear_action_status(self, msg_ref: str):
        if self.action_status == msg_ref:
            self.action_status = ""
            self.refresh_status_label()

    def show_status_message(self, msg: str):
        # 模型后台线程回调
        self.set_model_status(msg)

    def copy_history_item(self, text: str):
        print(f"[Copy] recv type={type(text)} len={len(text or '')} value='{text}'")
        t = (text or "").strip()
        if not t:
            self.set_action_status("内容为空")
            return
        try:
            # 先只用 Qt 剪贴板
            QApplication.clipboard().setText(t)
            self.set_action_status("已复制")
        except Exception as e:
            print("[CopyError]", e)
            self.set_action_status("复制失败")
    def rebuild_history_ui(self):
        for i in reversed(range(self.history_layout.count() - 1)):
            item = self.history_layout.itemAt(i)
            w = item.widget() if item else None
            if w:
                self.history_layout.removeWidget(w)
                w.setParent(None)
                w.deleteLater()
        for t in self.history:
            self.history_layout.insertWidget(self.history_layout.count() - 1, self.create_history_row(t))
        self.update_history_ui()

    def create_history_row(self, t: str):
        from functools import partial
        row = QWidget(self.history_container)
        row._latex_text = t
        hl = QHBoxLayout(row)
        hl.setContentsMargins(6, 4, 6, 4)
        lbl = QLabel(t)
        lbl.setWordWrap(True)
        hl.addWidget(lbl, 1)

        def add_btn(text, tip, handler_name, handler):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.setStyleSheet(ACTION_BTN_STYLE)
            b.clicked.connect(partial(self._safe_call, handler_name, handler))
            hl.addWidget(b)
            return b
        add_btn("预览", "渲染预览", "preview",
                lambda r=row: self.preview_formula(r._latex_text))
        add_btn("复制", "复制到剪贴板", "copy",
                lambda r=row: self.copy_history_item(r._latex_text))
        add_btn("收藏", "加入收藏夹", "favorite",
                lambda r=row: self.favorites_window.add_favorite(r._latex_text))
        add_btn("删除", "删除该条记录", "delete",
                lambda r=row: self.delete_history_item(r, r._latex_text))
        return row
    def add_history_record(self, text: str):
        t = (text or "").strip()
        if not t:
            return
        # 允许重复；如需“去重并上浮”可替换为： if t in self.history: self.history.remove(t)
        self.history.append(t)
        # 限制长度
        if len(self.history) > MAX_HISTORY:
            self.history = self.history[-MAX_HISTORY:]
        self.save_history()
        self.rebuild_history_ui()
        self.set_action_status("已加入历史")
        print(f"[HistoryAdd] total={len(self.history)} last='{t[:60]}'")
    def load_history(self):
        if not os.path.exists(self.history_path):
            return
        try:
            with open(self.history_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                # 过滤非字符串
                self.history = [str(x) for x in data if isinstance(x, (str, int, float))]
        except Exception as e:
            print("加载历史失败:", e)
            self.history = []
        self.rebuild_history_ui()
    def delete_history_item(self, widget, text):
        print(f"[Delete] request text='{text}' history_len={len(self.history)}")
        if text in self.history:
            self.history.remove(text)
        if widget:
            self.history_layout.removeWidget(widget)
            widget.setParent(None)
            widget.deleteLater()
        self.save_history()
        self.set_action_status("已删除")
        self.update_history_ui()

    def update_history_ui(self):
        if self.history:
            self.clear_history_button.setEnabled(True)
            self.clear_history_button.setToolTip("清空所有历史记录")
        else:
            self.clear_history_button.setEnabled(False)
            self.clear_history_button.setToolTip("当前无历史记录")

    def save_history(self):
        try:
            with open(self.history_path, "w", encoding="utf-8") as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print("历史保存失败:", e)

    # ---------- 模型/预测 ----------
    def on_model_changed(self, model_name: str):
        m = model_name.lower()
        if m not in ("pix2tex", "pix2text"):
            QMessageBox.warning(self, "错误", "未知模型，使用 pix2tex")
            m = "pix2tex"
        self.current_model = m
        self.cfg.set("default_model", m)
        self.set_model_status("已加载")
        if self.settings_window:
            self.settings_window.update_model_buttons()

    def start_capture(self):
        if not self.model:
            QMessageBox.warning(self, "错误", "模型未初始化")
            return
        self.overlay = ScreenCaptureOverlay()
        self.overlay.installEventFilter(self)
        self.overlay.selection_done.connect(self.on_capture_done)
        self.overlay.show()
        self.overlay.raise_()
        self.overlay.activateWindow()

    def eventFilter(self, obj, event):
        if obj is getattr(self, "overlay", None) and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                try:
                    obj.close()
                except Exception:
                    pass
                self.overlay = None
                self.set_action_status("已取消截图")
                return True
        return super().eventFilter(obj, event)

    def on_capture_done(self, pixmap):
        if self.overlay:
            self.overlay.close()
            self.overlay = None
        if pixmap is None:
            return
        if self._predict_busy:
            QMessageBox.information(self, "提示", "正在识别，请稍候")
            return
        try:
            img = self._qpixmap_to_pil(pixmap)
        except Exception as e:
            QMessageBox.warning(self, "错误", f"图片处理失败: {e}")
            return
        if not self.model:
            QMessageBox.warning(self, "错误", "模型未初始化")
            return
        if self.predict_thread and self.predict_thread.isRunning():
            QMessageBox.warning(self, "错误", "前一识别线程尚未结束")
            return
        self._predict_busy = True
        self.set_model_status("识别中...")

        self.predict_thread = QThread()
        self.predict_worker = PredictionWorker(self.model, img, self.current_model)
        self.predict_worker.moveToThread(self.predict_thread)

        def _cleanup():
            self._predict_busy = False
            if self.predict_worker:
                self.predict_worker.deleteLater()
                self.predict_worker = None
            if self.predict_thread:
                self.predict_thread.deleteLater()
                self.predict_thread = None

        self.predict_thread.started.connect(self.predict_worker.run)
        self.predict_worker.finished.connect(self.on_predict_ok)
        self.predict_worker.failed.connect(self.on_predict_fail)
        self.predict_worker.finished.connect(self.predict_thread.quit)
        self.predict_worker.failed.connect(self.predict_thread.quit)
        self.predict_thread.finished.connect(_cleanup)
        self.predict_thread.start()

    def on_predict_ok(self, latex: str):
        self.set_model_status("完成")
        self.show_confirm_dialog(latex)

    def on_predict_fail(self, msg: str):
        self.set_model_status("失败")
        QMessageBox.warning(self, "错误", msg)

    # ---------- 结果确认 & 预览 ----------
    def show_confirm_dialog(self, latex_code: str):
        code = (latex_code or "").strip()
        if not code:
            QMessageBox.information(self, "提示", "结果为空")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("识别结果")
        dlg.resize(820, 360)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("确认或修改 LaTeX："))
        te = QTextEdit()
        te.setText(code)
        if DISABLE_WEBENGINE_PREVIEW:
            lay.addWidget(te)
        else:
            splitter = QSplitter(Qt.Orientation.Horizontal)
            splitter.addWidget(te)
            v = self._create_webengine_view()
            if v:
                container = QWidget()
                vl = QVBoxLayout(container); vl.setContentsMargins(0,0,0,0)
                vl.addWidget(v)
                splitter.addWidget(container)
                splitter.setSizes([430, 380])
                self._render_latex_html(v, code)
                te.textChanged.connect(lambda: self._render_latex_html(v, te.toPlainText()))
                lay.addWidget(splitter)
            else:
                lay.addWidget(te)

        btn = QPushButton("确定")
        btn.setStyleSheet(BTN_PRIMARY)
        btn.clicked.connect(lambda: self.accept_latex(dlg, te))
        lay.addWidget(btn)
        dlg.exec()
    def accept_latex(self, dialog, te: QTextEdit):
        t = te.toPlainText().strip()
        if not t:
            dialog.reject()
            return
        try:
            try:
                pyperclip.copy(t)
            except Exception:
                QApplication.clipboard().setText(t)
        except Exception as e:
            QMessageBox.warning(self, "错误", f"复制失败: {e}")
        try:
            self.add_history_record(t)
        except Exception as e:
            QMessageBox.warning(self, "错误", f"写入历史失败: {e}")
        dialog.accept()

    def preview_formula(self, text: str):
        t = (text or "").strip()
        if not t:
            QMessageBox.information(self, "提示", "内容为空")
            return
        if DISABLE_WEBENGINE_PREVIEW:
            QMessageBox.information(self, "预览(纯文本)", t)
            return
        v = self._create_webengine_view()
        if not v:
            QMessageBox.information(self, "预览(降级)", t)
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("公式预览")
        dlg.resize(620, 300)
        lay = QVBoxLayout(dlg)
        lay.addWidget(v)
        self._render_latex_html(v, t)
        b = QPushButton("关闭"); b.setStyleSheet(BTN_PRIMARY); b.clicked.connect(dlg.accept)
        lay.addWidget(b)
        dlg.exec()
    def clear_history(self):
        if not self.history:
            self.set_action_status("无历史记录")
            return
        ret = QMessageBox.question(
            self, "确认", "确定清空全部历史记录？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if ret == QMessageBox.StandardButton.Yes:
            self.history.clear()
            self.save_history()
            self.rebuild_history_ui()
            self.set_action_status("已清空历史")
    def register_hotkey(self, seq: str):
        if not self.hotkey:
            # 全局热键已禁用，忽略
            return
        print(f"[Hotkey] try register {seq}")
        try:
            self.hotkey.setShortcut(QKeySequence(seq))
            self.hotkey.register()
            print(f"[Hotkey] global registered={self.hotkey.is_registered()}")
            if self._fallback_shortcut:
                try:
                    self._fallback_shortcut.activated.disconnect()
                except Exception:
                    pass
                self._fallback_shortcut.setParent(None)
                self._fallback_shortcut = None
        except Exception as e:
            print(f"[Hotkey] global failed: {e}")
            if not self._fallback_shortcut:
                self._fallback_shortcut = QShortcut(QKeySequence(seq), self)
                self._fallback_shortcut.activated.connect(self.start_capture)
                print("[Hotkey] fallback QShortcut enabled")

    def on_hotkey_triggered(self):
        print("[Hotkey] Triggered")
        self.start_capture()

    def set_shortcut(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("设置快捷键")
        dlg.resize(320, 120)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(f"当前: {self.cfg.get('hotkey','Ctrl+F')}   按下新的 Ctrl+字母以创建"))
        edit = QTextEdit()
        edit.setReadOnly(True)
        edit.setFixedHeight(34)

        def keyPressEvent(ev):
            k = ev.key()
            if ev.modifiers() & Qt.KeyboardModifier.ControlModifier and Qt.Key.Key_A <= k <= Qt.Key.Key_Z:
                edit.setText(f"Ctrl+{chr(k)}")
            else:
                edit.setText("")
        edit.keyPressEvent = keyPressEvent
        lay.addWidget(edit)
        btn = QPushButton("确定")
        btn.setStyleSheet(BTN_PRIMARY)
        btn.clicked.connect(lambda: self.update_hotkey(edit.toPlainText().strip(), dlg))
        lay.addWidget(btn)
        dlg.exec()

    def update_hotkey(self, text: str, dialog: QDialog):
        if not (text.startswith("Ctrl+") and len(text) == 6 and text[-1].isalpha()):
            QMessageBox.warning(self, "错误", "格式必须 Ctrl+字母")
            return
        self.register_hotkey(text)
        # 兼容禁用全局热键的场景
        if self.hotkey and (not self.hotkey.is_registered()) and not self._fallback_shortcut:
            QMessageBox.warning(self, "错误", "快捷键注册失败")
            return
        self.cfg.set("hotkey", text)
        dialog.accept()
        QMessageBox.information(self, "提示", f"已更新: {text}")

    # ---------- 其它 UI ----------
    def open_settings(self):
        if self.settings_window and self.settings_window.isVisible():
            self.settings_window.raise_()
            self.settings_window.activateWindow()
            return
        if not self.settings_window:
            self.settings_window = SettingsWindow(self)
            self.settings_window.model_changed.connect(self.on_model_changed)
            self.settings_window.destroyed.connect(lambda: setattr(self, "settings_window", None))
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    def open_favorites(self):
        self.favorites_window.show()
        self.favorites_window.raise_()
        self.favorites_window.activateWindow()

    def show_window(self):
        self.show()
        self.raise_()
        self.activateWindow()

    # ---------- 关闭 / 资源清理 ----------
    def _cleanup_webengine_views(self):
        if DISABLE_WEBENGINE_PREVIEW or not QWebEngineView:
            return
        try:
            if hasattr(self, "history_container"):
                for v in self.history_container.findChildren(QWebEngineView):
                    v.setParent(None)
                    v.deleteLater()
            if self.favorites_window:
                for v in self.favorites_window.render_container.findChildren(QWebEngineView):
                    v.setParent(None)
                    v.deleteLater()
        except Exception:
            pass

    def _graceful_shutdown(self):
        if getattr(self, "_shutdown_done", False):
            return
        if self.predict_thread:
            try:
                if self.predict_thread.isRunning():
                    self.predict_thread.quit()
                    self.predict_thread.wait(1500)
            except Exception:
                pass
        if self.predict_worker:
            try:
                self.predict_worker.deleteLater()
            except Exception:
                pass
        self.predict_thread = None
        self.predict_worker = None
        self._predict_busy = False
    # ------ 5) 修改 closeEvent（替换原实现） ------
    def closeEvent(self, event):
        if self._force_exit:
            # 真实退出
            self._graceful_shutdown()
            event.accept()
            return
        # 普通关闭 = 最小化到托盘
        self.hide()
        if self.tray_icon:
            self.tray_icon.showMessage("LaTeXSnipper", "已最小化到托盘")
        event.ignore()

    # ------ 6) 修改 truly_exit（替换原实现） ------
    def truly_exit(self):
        self._force_exit = True
        if self.tray_icon:
            self.tray_icon.hide()
        # 先关闭窗口（触发 closeEvent 分支），再延迟真正退出
        try:
            self.close()
        except Exception:
            pass
        QTimer.singleShot(0, lambda: (self._graceful_shutdown(), QCoreApplication.quit()))
    def _create_webengine_view(self):
        if DISABLE_WEBENGINE_PREVIEW:
            return None
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
            v = QWebEngineView()
            v.setHtml("<html><body style='font-size:12px;background:#f0f0f0;color:#666;'>初始化...</body></html>")
            return v
        except Exception as e:
            print("[WebEngineCreateFail]", e)
            return None

    def _render_latex_html(self, view, latex: str):
        if not view:
            return
        try:
            from PyQt6.QtCore import QTimer
            html = build_math_html(latex or "")
            QTimer.singleShot(0, lambda: view.setHtml(html))
        except Exception as e:
            print("[WebEngineRenderFail]", e)
class PredictionWorker(QObject):
    finished = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, model_wrapper: ModelWrapper, image: Image.Image, model_name: str):
        super().__init__()
        self.model_wrapper = model_wrapper
        self.image = image
        self.model_name = model_name

    def run(self):
        try:
            res = self.model_wrapper.predict(self.image, model_name=self.model_name)
            if not res or not res.strip():
                self.failed.emit("识别结果为空")
            else:
                self.finished.emit(res.strip())
        except Exception as e:
            self.failed.emit(str(e))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())