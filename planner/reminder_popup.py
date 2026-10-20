"""Немодальное окно напоминаний, видимое поверх обычных окон."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout,
)


class ReminderPopup(QDialog):
    open_planner = Signal()

    def __init__(self):
        # Без родителя: окно остаётся видимым, когда ежедневник скрыт в трее.
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setObjectName("reminderPopup")
        self.setWindowTitle("Напоминания — Лист")
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setModal(False)
        self.resize(500, 350)
        self.setMinimumSize(400, 280)
        self.messages: list[str] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(14)
        self.heading = QLabel("Напоминание", objectName="section")
        layout.addWidget(self.heading)
        self.details = QTextEdit()
        self.details.setObjectName("reminderText")
        self.details.setReadOnly(True)
        self.details.setAcceptRichText(False)
        layout.addWidget(self.details, 1)
        actions = QHBoxLayout()
        open_button = QPushButton("Открыть ежедневник")
        open_button.clicked.connect(self.open_and_close)
        actions.addWidget(open_button)
        actions.addStretch()
        self.dismiss_button = QPushButton("Понятно", objectName="primary")
        self.dismiss_button.clicked.connect(self.accept)
        actions.addWidget(self.dismiss_button)
        layout.addLayout(actions)
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            self.move(area.center() - self.rect().center())

    def add_message(self, title: str, body: str) -> None:
        self.messages.append(title + "\n" + body)
        self.heading.setText("Напоминание" if len(self.messages) == 1 else f"Напоминания · {len(self.messages)}")
        # Только обычный текст: название или заметка могут содержать HTML.
        self.details.setPlainText("\n\n----------------------------\n\n".join(self.messages))
        self.details.moveCursor(QTextCursor.MoveOperation.End)
        self.show()
        self.raise_()
        self.activateWindow()
        QApplication.alert(self)

    def open_and_close(self) -> None:
        self.open_planner.emit()
        self.accept()
