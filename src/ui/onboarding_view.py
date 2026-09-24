"""Native Fluent tour card and main-window spotlight surface."""

from PyQt6.QtCore import QPoint, QRect, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    FluentIcon,
    PrimaryPushButton,
    ProgressRing,
    PushButton,
    SubtitleLabel,
    TransparentToolButton,
    isDarkTheme,
    themeColor,
)

from localization.manager import translate as tr


class TourSurface(QWidget):
    nextRequested = pyqtSignal()
    backRequested = pyqtSignal()
    exitRequested = pyqtSignal()
    actionRequested = pyqtSignal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.targets = []
        self.card = QFrame(self)
        self.card.setObjectName("tourCard")
        layout = QVBoxLayout(self.card)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        header = QHBoxLayout()
        self.brand = BodyLabel("LaTeXSnipper", self.card)
        header.addWidget(self.brand)
        header.addStretch()
        self.counter = BodyLabel(self.card)
        header.addWidget(self.counter)
        self.close_button = TransparentToolButton(FluentIcon.CLOSE, self.card)
        self.close_button.setAccessibleName(tr("关闭引导"))
        self.close_button.setToolTip(tr("关闭引导"))
        self.close_button.clicked.connect(self.exitRequested)
        header.addWidget(self.close_button)
        layout.addLayout(header)
        self.hero = QLabel(self.card)
        self.hero.setFixedHeight(64)
        layout.addWidget(self.hero)
        self.title = SubtitleLabel(self.card)
        self.title.setWordWrap(True)
        layout.addWidget(self.title)
        self.description = BodyLabel(self.card)
        self.description.setWordWrap(True)
        layout.addWidget(self.description)
        self.detail = BodyLabel(self.card)
        self.detail.setWordWrap(True)
        layout.addWidget(self.detail)
        self.ring = ProgressRing(self.card)
        self.ring.setFixedSize(28, 28)
        layout.addWidget(self.ring)
        self.actions_widget = QWidget(self.card)
        self.actions = QVBoxLayout(self.actions_widget)
        self.actions.setContentsMargins(0, 0, 0, 0)
        self.actions.setSpacing(8)
        layout.addWidget(self.actions_widget)
        footer = QHBoxLayout()
        self.back = PushButton(tr("上一步"), self.card)
        self.back.clicked.connect(self.backRequested)
        footer.addWidget(self.back)
        footer.addStretch()
        self.skip = PushButton(tr("跳过"), self.card)
        self.skip.clicked.connect(self.exitRequested)
        footer.addWidget(self.skip)
        self.next = PrimaryPushButton(tr("下一步"), self.card)
        self.next.clicked.connect(self.nextRequested)
        footer.addWidget(self.next)
        layout.addLayout(footer)

    def set_content(self, step, index, count, actions, detail=""):
        self.title.setText(step.title)
        self.description.setText(step.description)
        self.detail.setText(detail)
        self.detail.setVisible(bool(detail))
        self.counter.setText(f"{index + 1:02d} / {count:02d}")
        self.hero.setPixmap(getattr(FluentIcon, step.icon).icon().pixmap(48, 48))
        self.hero.show()
        self.back.setText(tr("上一步"))
        self.back.setVisible(index > 0)
        self.skip.show()
        self.next.setText(
            tr("开始使用")
            if index == count - 1
            else tr("开始引导")
            if index == 0
            else tr("下一步")
        )
        while self.actions.count():
            self.actions.takeAt(0).widget().deleteLater()
        for key, label in actions:
            button = PushButton(label, self.actions_widget)
            button.setFixedHeight(36)
            button.clicked.connect(
                lambda checked=False, key=key: self.actionRequested.emit(key)
            )
            self.actions.addWidget(button)
        self.actions_widget.setMinimumHeight(
            len(actions) * 36 + max(0, len(actions) - 1) * 8
        )
        self.actions_widget.setVisible(bool(actions))
        self.apply_theme()
        self.reposition()
        self.next.setFocus()

    def show_exit(self):
        self.title.setText(tr("退出快速入门？"))
        self.description.setText(tr("需要重看时，点击主窗口“快速入门”。"))
        self.hero.hide()
        self.detail.hide()
        self.ring.hide()
        self.actions_widget.hide()
        self.back.show()
        self.back.setText(tr("继续引导"))
        self.skip.hide()
        self.next.setText(tr("退出引导"))
        self.targets = []
        self.reposition()
        self.back.setFocus()

    def apply_theme(self):
        dark = isDarkTheme()
        background = "#25282e" if dark else "#ffffff"
        border = "#454b55" if dark else "#dce3ed"
        self.card.setStyleSheet(
            f"QFrame#tourCard {{ background: {background}; border: 1px solid {border}; border-radius: 18px; }}"
        )
        self.brand.setStyleSheet(f"color: {themeColor().name()}; font-weight: 600;")
        self.update()

    def target_rects(self):
        return [
            QRectF(
                QRect(self.mapFromGlobal(widget.mapToGlobal(QPoint())), widget.size())
            ).adjusted(-5, -5, 5, 5)
            for widget in self.targets
            if widget.isVisible()
        ]

    def reposition(self):
        self.setGeometry(self.parentWidget().rect())
        self.card.setFixedWidth(min(500, max(280, self.width() - 40)))
        self.card.adjustSize()
        x = (self.width() - self.card.width()) // 2
        y = (self.height() - self.card.height()) // 2
        targets = self.target_rects()
        if targets:
            target = targets[0]
            if target.right() + 24 + self.card.width() < self.width() - 20:
                x = int(target.right() + 24)
            elif target.left() - 24 - self.card.width() > 20:
                x = int(target.left() - 24 - self.card.width())
            y = min(
                max(20, int(target.center().y() - self.card.height() / 2)),
                max(20, self.height() - self.card.height() - 20),
            )
        self.card.move(x, max(20, y))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        mask = QPainterPath()
        mask.addRect(QRectF(self.rect()))
        for rect in self.target_rects():
            hole = QPainterPath()
            hole.addRoundedRect(rect, 8, 8)
            mask = mask.subtracted(hole)
        painter.fillPath(mask, QColor(0, 0, 0, 145))
        painter.setPen(QPen(themeColor(), 2))
        for rect in self.target_rects():
            painter.drawRoundedRect(rect, 8, 8)

    def focusNextPrevChild(self, forward):
        current = QApplication.focusWidget() or self.next
        candidate = current
        while True:
            candidate = (
                candidate.nextInFocusChain()
                if forward
                else candidate.previousInFocusChain()
            )
            if candidate is current:
                return True
            if (
                self.card.isAncestorOf(candidate)
                and candidate.isVisible()
                and candidate.isEnabled()
                and candidate.focusPolicy() & Qt.FocusPolicy.TabFocus
            ):
                candidate.setFocus(
                    Qt.FocusReason.TabFocusReason
                    if forward
                    else Qt.FocusReason.BacktabFocusReason
                )
                return True

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.exitRequested.emit()
        else:
            super().keyPressEvent(event)
