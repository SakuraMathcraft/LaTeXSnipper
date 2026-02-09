# backend/capture_overlay.py
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import pyqtSignal, Qt, QRect
from PyQt6.QtGui import QPainter, QColor, QPen, QGuiApplication, QFont, QFontMetrics

class ScreenCaptureOverlay(QWidget):
    selection_done = pyqtSignal(object)  # 发射 QPixmap

    def __init__(self):
        super().__init__()
        self.start_pos = None
        self.end_pos = None
        self.current_pos = None
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setWindowTitle("Screen Capture Overlay")

        # 覆盖整个屏幕
        screen = QGuiApplication.primaryScreen()
        self.setGeometry(screen.geometry())
        self.setMouseTracking(True)

    def _selection_rect(self) -> QRect | None:
        if not self.start_pos or not self.end_pos:
            return None
        return QRect(self.start_pos, self.end_pos).normalized()

    def _selection_size(self) -> tuple[int, int]:
        if not self.start_pos or not self.end_pos:
            return (0, 0)
        width = abs(int(self.end_pos.x() - self.start_pos.x()))
        height = abs(int(self.end_pos.y() - self.start_pos.y()))
        return (width, height)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 95))  # 外围变暗，更聚焦
        rect = self._selection_rect()

        # 选框内保持原亮度（清除遮罩）
        if rect:
            painter.save()
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(rect, Qt.GlobalColor.transparent)
            painter.restore()

        # 鼠标十字准星
        if self.current_pos:
            cross_pen = QPen(QColor(255, 255, 255, 180), 1)
            painter.setPen(cross_pen)
            # 使用局部短十字，避免贯穿整屏造成干扰
            arm = 12
            cx, cy = self.current_pos.x(), self.current_pos.y()
            painter.drawLine(cx - arm, cy, cx + arm, cy)
            painter.drawLine(cx, cy - arm, cx, cy + arm)

        if rect:
            pen = QPen(QColor(0, 170, 255), 2)
            painter.setPen(pen)
            painter.drawRect(rect)

            # 尺寸与坐标标注（类似 Snipaste：宽x高 + 左上角坐标）
            width, height = self._selection_size()
            if width > 0 and height > 0:
                gx = int(self.geometry().x() + rect.left())
                gy = int(self.geometry().y() + rect.top())
                text = f"{width} x {height}  ({gx}, {gy})"
                font = QFont("Segoe UI", 10)
                painter.setFont(font)
                fm = QFontMetrics(font)

                label_padding_x = 8
                label_h = fm.height() + 6
                label_w = fm.horizontalAdvance(text) + label_padding_x * 2

                label_x = rect.left()
                label_y = rect.top() - label_h - 6
                if label_y < 2:
                    label_y = rect.top() + 6
                max_x = max(2, self.width() - label_w - 2)
                label_x = max(2, min(label_x, max_x))
                max_y = max(2, self.height() - label_h - 2)
                label_y = max(2, min(label_y, max_y))

                label_rect = QRect(label_x, label_y, label_w, label_h)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(0, 170, 255, 230))
                painter.drawRoundedRect(label_rect, 4, 4)

                painter.setPen(QColor(255, 255, 255))
                painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, text)

    def mousePressEvent(self, event):
        self.current_pos = event.position().toPoint()
        self.start_pos = self.current_pos
        self.end_pos = self.start_pos
        self.update()

    def mouseMoveEvent(self, event):
        self.current_pos = event.position().toPoint()
        if self.start_pos:
            self.end_pos = self.current_pos
        self.update()

    def mouseReleaseEvent(self, event):
        self.current_pos = event.position().toPoint()
        self.end_pos = self.current_pos
        self.update()
        self.capture_selection()

    def capture_selection(self):
        if not self.start_pos or not self.end_pos:
            self.selection_done.emit(None)
            return
        rect = self._selection_rect()
        if rect is None:
            self.selection_done.emit(None)
            return
        x1, y1 = int(rect.left()), int(rect.top())
        width, height = self._selection_size()
        if width <= 0 or height <= 0:
            self.selection_done.emit(None)
            return

        screen = QGuiApplication.primaryScreen()
        pixmap = screen.grabWindow(0, x1, y1, width, height)
        print(f"[Overlay] Captured pixmap size: {pixmap.width()}x{pixmap.height()}")  # 日志输出

        self.selection_done.emit(pixmap)
