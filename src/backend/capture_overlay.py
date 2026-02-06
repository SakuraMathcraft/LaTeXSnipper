# backend/capture_overlay.py
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import pyqtSignal, Qt, QRect
from PyQt6.QtGui import QPainter, QColor, QPen, QScreen, QGuiApplication

class ScreenCaptureOverlay(QWidget):
    selection_done = pyqtSignal(object)  # 发射 QPixmap

    def __init__(self):
        super().__init__()
        self.start_pos = None
        self.end_pos = None
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setWindowTitle("Screen Capture Overlay")

        # 覆盖整个屏幕
        screen = QGuiApplication.primaryScreen()
        self.setGeometry(screen.geometry())
        self.setMouseTracking(True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 50))  # 半透明黑色遮罩
        if self.start_pos and self.end_pos:
            pen = QPen(QColor(0, 170, 255), 2)
            painter.setPen(pen)
            rect = QRect(self.start_pos, self.end_pos)
            painter.drawRect(rect.normalized())

    def mousePressEvent(self, event):
        self.start_pos = event.position().toPoint()
        self.end_pos = self.start_pos
        self.update()

    def mouseMoveEvent(self, event):
        if self.start_pos:
            self.end_pos = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        self.end_pos = event.position().toPoint()
        self.update()
        self.capture_selection()

    def capture_selection(self):
        if not self.start_pos or not self.end_pos:
            self.selection_done.emit(None)
            return

        x1 = int(min(self.start_pos.x(), self.end_pos.x()))
        y1 = int(min(self.start_pos.y(), self.end_pos.y()))
        x2 = int(max(self.start_pos.x(), self.end_pos.x()))
        y2 = int(max(self.start_pos.y(), self.end_pos.y()))
        width = x2 - x1
        height = y2 - y1

        screen = QGuiApplication.primaryScreen()
        pixmap = screen.grabWindow(0, x1, y1, width, height)
        print(f"[Overlay] Captured pixmap size: {pixmap.width()}x{pixmap.height()}")  # 日志输出

        self.selection_done.emit(pixmap)
