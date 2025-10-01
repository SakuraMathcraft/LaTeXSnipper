import sys
import os
import threading
from io import BytesIO
import pyperclip
from PIL import Image
from pynput import keyboard as pynput_keyboard

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QListWidget, QLabel,
    QSystemTrayIcon, QMenu, QDialog, QTextEdit, QHBoxLayout, QListWidgetItem,
    QMessageBox, QInputDialog, QScrollArea
)
from PyQt6.QtGui import QIcon, QEnterEvent
from PyQt6.QtCore import QBuffer, QIODevice, QTimer, Qt, QPropertyAnimation, QEasingCurve, pyqtSignal

sys.path.append(os.path.join(os.path.dirname(__file__), "backend"))
from backend.capture_overlay import ScreenCaptureOverlay
from backend.model import ModelWrapper

# ---------------- Hover 动画控件 ----------------
class HoverWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.base_style = """
            QWidget {
                background-color:#fefefe;
                border:1px solid #ddd;
                border-radius:5px;
            }
        """
        self.hover_style = """
            QWidget {
                background-color:#fefefe;
                border:1px solid #bbb;
                border-radius:5px;
                box-shadow: 3px 3px 10px rgba(0,0,0,0.2);
            }
        """
        self.setStyleSheet(self.base_style)
        self.animation = None  # 先不创建动画

    def showEvent(self, event):
        if not self.animation:
            self.animation = QPropertyAnimation(self, b"windowOpacity")
            self.animation.setDuration(150)
            self.animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        super().showEvent(event)

    def enterEvent(self, event):
        if self.animation:
            self.animation.stop()
            self.setStyleSheet(self.hover_style)
            self.animation.setStartValue(0.8)
            self.animation.setEndValue(1.0)
            self.animation.start()

    def leaveEvent(self, event):
        if self.animation:
            self.animation.stop()
            self.setStyleSheet(self.base_style)
            self.animation.setStartValue(1.0)
            self.animation.setEndValue(0.8)
            self.animation.start()

import os
import json
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QListWidget, QListWidgetItem, QMenu, QInputDialog,
    QPushButton, QMessageBox, QFileDialog
)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt

class FavoritesWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("公式收藏夹")
        self.setMinimumSize(400, 300)
        self.setWindowFlags(Qt.WindowType.Window)

        icon_path = os.path.join(os.path.dirname(__file__), "assets", "icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.layout = QVBoxLayout()
        self.list_widget = QListWidget()
        self.layout.addWidget(self.list_widget)

        # 添加选择保存路径按钮
        self.select_path_button = QPushButton("选择收藏夹保存路径")
        self.select_path_button.clicked.connect(self.select_file)
        self.select_path_button.setStyleSheet("""
            QPushButton {
                background-color:#3daee9;
                color:white;
                font-size:14px;
                padding:6px;
                border-radius:5px;
            }
            QPushButton:hover {
                background-color:#5dbff2;
            }
        """)
        self.layout.addWidget(self.select_path_button)

        self.setLayout(self.layout)

        self.favorites = []
        self.file_path = None  # 用户选择的保存路径

        # 右键菜单
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self.show_context_menu)

        # 加载收藏夹
        self.load_favorites()

    # ---------------- 文件操作 ----------------
    def select_file(self):
        path, _ = QFileDialog.getSaveFileName(self, "选择收藏夹保存路径", os.getcwd(), "JSON Files (*.json)")
        if path:
            self.file_path = path
            self.save_favorites()
            QMessageBox.information(self, "提示", f"收藏夹将保存到：{self.file_path}")

    def load_favorites(self):
        if not self.file_path:
            # 默认保存到项目路径
            self.file_path = os.path.join(os.path.dirname(__file__), "favorites.json")
            if not os.path.exists(self.file_path):
                # 提示用户
                QMessageBox.information(
                    self, "提示", f"收藏夹未选择路径，将自动保存到项目路径：\n{self.file_path}"
                )

        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    self.favorites = json.load(f)
            except:
                self.favorites = []
        self.refresh_list()

    def save_favorites(self):
        if not self.file_path:
            return
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.favorites, f, ensure_ascii=False, indent=2)
        except Exception as e:
            QMessageBox.warning(self, "错误", f"保存收藏夹失败: {e}")

    # ---------------- 收藏操作 ----------------
    def add_favorite(self, text):
        text = text.strip()
        if not text or text in self.favorites:
            return
        self.favorites.append(text)
        self.refresh_list()
        self.save_favorites()
        self.show()
        self.raise_()
        self.activateWindow()

    def refresh_list(self):
        self.list_widget.clear()
        for item in self.favorites:
            self.list_widget.addItem(QListWidgetItem(item))

    def show_context_menu(self, pos):
        item = self.list_widget.itemAt(pos)
        if item:
            menu = QMenu()
            menu.setStyleSheet("""
                QMenu {
                    font-size: 14px;
                }
                QMenu::item {
                    padding: 6px 20px;
                    text-align: center;   /* 关键：居中对齐 */
                }
                QMenu::item:selected {
                    background-color: #3daee9;
                    color: white;
                    border-radius: 4px;
                }
            """)
            delete_action = menu.addAction("删除")
            edit_action = menu.addAction("编辑")
            action = menu.exec(self.list_widget.mapToGlobal(pos))
            if action == delete_action:
                self.favorites.remove(item.text())
                self.refresh_list()
                self.save_favorites()
            elif action == edit_action:
                new_text, ok = QInputDialog.getText(
                    self, "编辑公式", "修改公式内容:", text=item.text()
                )
                if ok and new_text.strip():
                    idx = self.favorites.index(item.text())
                    self.favorites[idx] = new_text.strip()
                    self.refresh_list()
                    self.save_favorites()

# ---------------- 主窗口 ----------------
class MainWindow(QWidget):
    esc_pressed_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("LaTeXSnipper")
        self.setMinimumSize(500, 400)

        icon_path = os.path.join(os.path.dirname(__file__), "assets", "icon.ico")
        self.icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()
        self.setWindowIcon(self.icon)

        self.model = ModelWrapper()
        self.overlay = None
        self.history = []
        self.favorites_window = FavoritesWindow()  # 不传 parent

        # 快捷键状态
        self.ctrl_pressed = False
        self.shift_pressed = False
        self.alt_pressed = False
        self.custom_hotkey = {'ctrl': True, 'shift': False, 'alt': False, 'key': 's'}

        # ESC 信号连接
        self.esc_pressed_signal.connect(self.cancel_capture)

        # ---------------- UI ----------------
        self.capture_button = QPushButton("截图识别")
        self.capture_button.setStyleSheet(
            "QPushButton { background-color:#3daee9; color:white; font-size:16px; padding:10px; border-radius:5px; }"
            "QPushButton:hover { background-color:#5dbff2; }"
        )
        self.capture_button.clicked.connect(self.start_capture)
        # ---------------- 历史记录 ----------------
        history_label = QLabel("历史记录")
        history_label.setStyleSheet("font-weight:bold; font-size:16px;")

        # 改成 QScrollArea
        self.history_scroll = QScrollArea()
        self.history_scroll.setWidgetResizable(True)
        self.history_scroll.setStyleSheet("""
            QScrollArea { border:1px solid #ccc; border-radius:5px; background-color:#fdfdfd; }
            QScrollBar:vertical { background:#f0f0f0; width:12px; border-radius:6px; margin:0; }
            QScrollBar::handle:vertical { background:#3daee9; min-height:20px; border-radius:6px; }
            QScrollBar::handle:vertical:hover { background-color:#5dbff2; }
        """)
        self.history_container = QWidget()
        self.history_layout = QVBoxLayout(self.history_container)
        self.history_layout.setContentsMargins(0,0,0,0)
        self.history_layout.setSpacing(5)
        self.history_layout.addStretch()  # 保证内容靠上
        self.history_scroll.setWidget(self.history_container)

        # 清空历史按钮
        self.clear_history_button = QPushButton("清空历史记录")
        self.clear_history_button.setStyleSheet(
            "QPushButton { background-color:#3daee9; color:white; font-size:14px; padding:6px; border-radius:4px; }"
            "QPushButton:hover { background-color:#5dbff2; }"
        )
        self.clear_history_button.clicked.connect(self.clear_history)
        # 设置快捷键按钮
        self.change_key_button = QPushButton("设置快捷键")
        self.change_key_button.setStyleSheet(
            "QPushButton { background-color:#3daee9; color:white; font-size:14px; padding:6px; border-radius:4px; }"
            "QPushButton:hover { background-color:#5dbff2; }"
        )
        self.change_key_button.clicked.connect(self.set_shortcut)

        self.show_fav_button = QPushButton("打开收藏夹")
        self.show_fav_button.setStyleSheet(
            "QPushButton { background-color:#3daee9; color:white; font-size:14px; padding:6px; border-radius:4px; }"
            "QPushButton:hover { background-color:#5dbff2; }"
        )
        self.show_fav_button.clicked.connect(self.open_favorites)

        # 布局
        layout = QVBoxLayout()
        layout.addWidget(self.capture_button)
        layout.addWidget(history_label)
        layout.addWidget(self.history_scroll)
        layout.addWidget(self.clear_history_button)
        layout.addWidget(self.change_key_button)
        layout.addWidget(self.show_fav_button)
        self.setLayout(layout)
        # ---------------- 托盘 ----------------
        self.tray_icon = QSystemTrayIcon(self.icon, self)
        self.tray_menu = QMenu()
        self.tray_menu.addAction("打开主窗口", self.show_window)
        self.tray_menu.addAction("截图识别", self.start_capture)
        self.tray_menu.addAction("退出", self.close)
        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.show()

        # 全局快捷键监听
        threading.Thread(target=self.listen_hotkey, daemon=True).start()

    # ---------------- 收藏夹 ----------------
    def open_favorites(self):
        self.favorites_window.show()
        self.favorites_window.raise_()
        self.favorites_window.activateWindow()
        QMessageBox.information(self, "提示", "收藏夹已打开")

    # ---------------- ESC ----------------
    def cancel_capture(self):
        if self.overlay:
            self.overlay.close()
            self.overlay = None

    # ---------------- 快捷键监听 ----------------
    def listen_hotkey(self):
        def on_press(key):
            try:
                if key in (pynput_keyboard.Key.ctrl_l, pynput_keyboard.Key.ctrl_r):
                    self.ctrl_pressed = True
                if key == pynput_keyboard.Key.shift:
                    self.shift_pressed = True
                if key in (pynput_keyboard.Key.alt_l, pynput_keyboard.Key.alt_r):
                    self.alt_pressed = True
            except: pass

        def on_release(key):
            try:
                modifiers_ok = (
                    (not self.custom_hotkey['ctrl'] or self.ctrl_pressed) and
                    (not self.custom_hotkey['shift'] or self.shift_pressed) and
                    (not self.custom_hotkey['alt'] or self.alt_pressed)
                )
                key_char_ok = hasattr(key, "char") and key.char and key.char.lower() == self.custom_hotkey['key'].lower()
                if modifiers_ok and key_char_ok:
                    QTimer.singleShot(0, self.start_capture)

                # ESC 取消截图
                if key == pynput_keyboard.Key.esc and self.overlay:
                    QTimer.singleShot(0, self.esc_pressed_signal.emit)

                if key in (pynput_keyboard.Key.ctrl_l, pynput_keyboard.Key.ctrl_r):
                    self.ctrl_pressed = False
                if key == pynput_keyboard.Key.shift:
                    self.shift_pressed = False
                if key in (pynput_keyboard.Key.alt_l, pynput_keyboard.Key.alt_r):
                    self.alt_pressed = False
            except: pass

        with pynput_keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            listener.join()

    # ---------------- 设置快捷键 ----------------
    def set_shortcut(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("设置快捷键")
        dialog.setModal(True)
        dialog.resize(400, 150)
        dialog.setStyleSheet("""
            QLabel{font-size:14px;} 
            QPushButton{background-color:#3daee9;color:white;border-radius:4px;padding:6px;} 
            QPushButton:hover{background-color:#5dbff2;}
        """)
        layout = QVBoxLayout()
        layout.addWidget(QLabel("请输入组合键（如 Ctrl+Shift+S）别乱搞！目前这玩意极其容易他妈闪退我也不知道为啥！"))
        text_edit = QTextEdit()
        text_edit.setFixedHeight(30)
        text_edit.setText(self.get_hotkey_str())
        layout.addWidget(text_edit)
        btn_ok = QPushButton("确定")
        btn_ok.clicked.connect(lambda: self.update_hotkey_from_input(text_edit.toPlainText(), dialog))
        layout.addWidget(btn_ok)
        dialog.setLayout(layout)
        dialog.move(self.geometry().center() - dialog.rect().center())
        dialog.exec()

    def get_hotkey_str(self):
        parts = []
        if self.custom_hotkey['ctrl']: parts.append("Ctrl")
        if self.custom_hotkey['shift']: parts.append("Shift")
        if self.custom_hotkey['alt']: parts.append("Alt")
        parts.append(self.custom_hotkey['key'].upper())
        return "+".join(parts)

    def update_hotkey_from_input(self, text, dialog):
        text = text.strip().lower()
        if not text:
            QMessageBox.warning(self, "错误", "快捷键不能为空")
            return

        # 找出最后一个非修饰键字符
        key_char = text[-1]
        for char in reversed(text):
            if char.isalnum():  # 字母或数字
                key_char = char
                break

        self.custom_hotkey = {
            'ctrl': 'ctrl' in text,
            'shift': 'shift' in text,
            'alt': 'alt' in text,
            'key': key_char
        }
        dialog.accept()
        QMessageBox.information(self, "提示", f"已设置快捷键为 {self.get_hotkey_str()}")

    # ---------------- 截图 ----------------
    def start_capture(self):
        self.overlay = ScreenCaptureOverlay()
        self.overlay.selection_done.connect(self.on_capture_done)
        self.overlay.show()
        self.overlay.activateWindow()
        self.overlay.raise_()

    def on_capture_done(self, pixmap):
        if self.overlay:
            self.overlay.close()
            self.overlay = None
        if pixmap is None or pixmap.isNull():
            return
        try:
            buffer = QBuffer()
            buffer.open(QIODevice.OpenModeFlag.ReadWrite)
            pixmap.save(buffer, "PNG")
            img = Image.open(BytesIO(buffer.data())).convert("RGB")
        except:
            return
        try:
            latex_code = self.model.predict(img)
        except:
            return
        self.show_confirm_dialog(latex_code)

    def show_confirm_dialog(self, latex_code):
        dialog = QDialog(self)
        dialog.setWindowTitle("识别结果")
        dialog.setModal(True)
        dialog.resize(600, 250)
        dialog.setStyleSheet("""
            QDialog{background-color:#f0f0f0;}
            QLabel{font-size:14px;}
            QTextEdit{font-size:14px;border:1px solid #ccc;border-radius:5px;}
            QPushButton{background-color:#3daee9;color:white;padding:6px;border-radius:4px;}
            QPushButton:hover{background-color:#5dbff2;}
        """)
        layout = QVBoxLayout()
        layout.addWidget(QLabel("请确认或修正 LaTeX:"))
        text_edit = QTextEdit()
        text_edit.setText(latex_code)
        layout.addWidget(text_edit)
        btn_ok = QPushButton("确定")
        btn_ok.clicked.connect(lambda: self.accept_latex(dialog, text_edit))
        layout.addWidget(btn_ok)
        dialog.setLayout(layout)
        dialog.move(self.geometry().center() - dialog.rect().center())
        dialog.exec()

    def accept_latex(self, dialog, text_edit):
        text = text_edit.toPlainText().strip()
        if text:
            pyperclip.copy(text)
            self.history.append(text)
            self.add_history_record(text)
        dialog.accept()

    # ---------------- 历史记录 ----------------
    def add_history_record(self, text):
        item_widget = HoverWidget(parent=self.history_container)
        layout = QHBoxLayout(item_widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        label = QTextEdit(text, parent=item_widget)
        label.setReadOnly(False)
        label.setAcceptRichText(False)
        label.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        label.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        label.setStyleSheet("font-size:14px;border:none;")
        label.setFixedHeight(40)

        btn_copy = QPushButton("复制", parent=item_widget)
        btn_delete = QPushButton("删除", parent=item_widget)
        btn_fav = QPushButton("收藏", parent=item_widget)

        btn_copy.clicked.connect(lambda: self.copy_history_item(label.toPlainText()))
        btn_delete.clicked.connect(lambda: self.delete_history_item(item_widget))
        btn_fav.clicked.connect(lambda: self.favorites_window.add_favorite(label.toPlainText()))

        btn_style = "QPushButton {background-color:#3daee9;color:white;font-size:14px;padding:4px 8px;border-radius:4px;} QPushButton:hover {background-color:#5dbff2;}"
        btn_copy.setStyleSheet(btn_style)
        btn_delete.setStyleSheet(btn_style)
        btn_fav.setStyleSheet(btn_style)

        layout.addWidget(label, 1)
        layout.addWidget(btn_copy)
        layout.addWidget(btn_delete)
        layout.addWidget(btn_fav)

        self.history_layout.insertWidget(self.history_layout.count() - 1, item_widget)

    def copy_history_item(self, text):
        pyperclip.copy(text)
        QMessageBox.information(self, "提示", "LaTeX 已复制到剪贴板")

    def delete_history_item(self, widget):
        self.history_layout.removeWidget(widget)
        widget.setParent(None)
        QMessageBox.information(self, "提示", "已删除该条历史记录")

    def clear_history(self):
        for i in reversed(range(self.history_layout.count() - 1)):  # 最后一个 stretch 不删
            item = self.history_layout.itemAt(i).widget()
            if item:
                self.history_layout.removeWidget(item)
                item.setParent(None)
        self.history.clear()
        QMessageBox.information(self, "提示", "已清空所有历史记录")

    # ---------------- 窗口 ----------------
    def show_window(self):
        QTimer.singleShot(0, self._show_window)
    def _show_window(self):
        self.show()
        self.raise_()
        self.activateWindow()
    def closeEvent(self, event):
        self.tray_icon.hide()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
