from __future__ import annotations

import logging
import sqlite3
from datetime import date, datetime, timedelta

from PySide6.QtCore import QDate, QDateTime, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDateEdit, QFrame, QDialog, QDialogButtonBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMenu, QLayout,
    QMessageBox, QPushButton, QSystemTrayIcon, QTableWidget, QTableWidgetItem,
    QTextEdit, QTimeEdit, QVBoxLayout, QWidget, QScrollArea, QTabWidget, QSpinBox,
)

from .database import Repository
from .birthdays import age_text, age_summary
from .greetings import STYLE_NAMES
from .models import Event
from .notifications import SystemNotifier, TelegramNotifier, TelegramSettings
from .reminder_popup import ReminderPopup
from .scheduler import Scheduler
from .telegram_api import TelegramError, validate_settings
from .telegram_dispatcher import TelegramDispatcher
from .themes import DEFAULT_THEME, THEMES, THEME_NAMES, apply_theme


def make_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#235D48"))
    painter.drawRoundedRect(2, 2, 60, 60, 16, 16)
    painter.setBrush(QColor("#F6F8EF"))
    painter.drawRoundedRect(15, 18, 34, 33, 5, 5)
    painter.setPen(QColor("#235D48"))
    painter.setFont(QFont("Segoe UI", 21, QFont.Weight.Bold))
    painter.drawText(15, 20, 34, 31, Qt.AlignmentFlag.AlignCenter, "✓")
    painter.end()
    return QIcon(pixmap)


class MainWindow(QMainWindow):
    def __init__(self, repository: Repository):
        super().__init__()
        self.repository = repository
        self.editing_id: int | None = None
        self.last_date = date.today()
        self.exit_requested = False
        self.tray_hint_shown = False
        self.reminder_popup: ReminderPopup | None = None
        self.setWindowTitle("Лист — ежедневник")
        self.setWindowIcon(make_icon())
        self.resize(1240, 940)
        self.setMinimumSize(1100, 800)
        self.theme = apply_theme(repository.get_setting("theme", DEFAULT_THEME))
        self.build_ui()
        self.build_tray()
        self.telegram_notifier = TelegramNotifier(TelegramSettings(
            repository.get_setting("telegram_bot_token"), repository.get_setting("telegram_chat_id"),
        ))
        self.telegram_dispatcher = TelegramDispatcher(repository, self.telegram_notifier)
        self.scheduler = Scheduler(repository, [SystemNotifier(self.show_notification)])
        self.timer = QTimer(self)
        self.timer.setInterval(10000)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        self.telegram_timer = QTimer(self)
        self.telegram_timer.setInterval(1000)
        self.telegram_timer.timeout.connect(self.telegram_tick)
        self.telegram_timer.start()
        QApplication.instance().aboutToQuit.connect(self.shutdown_background)
        self.new_event()
        self.refresh()
        QTimer.singleShot(500, self.tick)

    def build_ui(self) -> None:
        root = QWidget(objectName="root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(30, 26, 30, 12)
        outer.setSpacing(18)

        top = QHBoxLayout()
        heading = QVBoxLayout()
        heading.setSpacing(4)
        heading.addWidget(QLabel("Л И С Т   /   Л И Ч Н Ы Е   П Л А Н Ы", objectName="eyebrow"))
        heading.addWidget(QLabel("Мой ежедневник", objectName="heading"))
        self.date_label = QLabel(objectName="subtitle")
        heading.addWidget(self.date_label)
        top.addLayout(heading)
        top.addStretch()
        test = QPushButton("Проверить уведомление")
        test.clicked.connect(lambda: self.show_notification("Лист · проверка", "Это окно появляется поверх других окон и остаётся до закрытия."))
        top.addWidget(test)
        self.settings_button = QPushButton("Настройки")
        self.settings_button.clicked.connect(self.show_settings)
        top.addWidget(self.settings_button)
        outer.addLayout(top)

        stats = QHBoxLayout()
        stats.setSpacing(14)
        self.today_value, today_card = self.stat_card("СОБЫТИЙ СЕГОДНЯ", "0")
        self.next_value, next_card = self.stat_card("БЛИЖАЙШЕЕ СОБЫТИЕ", "Пока нет планов", True)
        self.cleanup_value, cleanup_card = self.stat_card("СЛЕДУЮЩАЯ ОЧИСТКА", "При запуске")
        self.next_value.setObjectName("nextValue")
        stats.addWidget(today_card, 2)
        stats.addWidget(next_card, 4)
        stats.addWidget(cleanup_card, 2)
        outer.addLayout(stats)

        self.banner = QLabel("Напоминания появляются поверх окон. Telegram подключается в настройках → «Телеграм-бот».", objectName="banner")
        self.banner.setTextFormat(Qt.TextFormat.PlainText)
        self.banner.setWordWrap(True)
        outer.addWidget(self.banner)

        content = QHBoxLayout()
        content.setSpacing(22)
        left = QVBoxLayout()
        left.setSpacing(12)
        row = QHBoxLayout()
        row.addWidget(QLabel("Мои записи", objectName="section"))
        row.addStretch()
        new_button = QPushButton("+ Новая запись")
        new_button.clicked.connect(self.new_event)
        row.addWidget(new_button)
        left.addLayout(row)

        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск по названию и заметке…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh)
        self.filter = QComboBox()
        self.filter.addItems(["Все записи", "Сегодня", "Предстоящие", "Дни рождения", "Прошедшие"])
        self.filter.currentIndexChanged.connect(self.refresh)
        filters.addWidget(self.search, 3)
        filters.addWidget(self.filter, 2)
        left.addLayout(filters)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["СОБЫТИЕ", "ДАТА И ВРЕМЯ", "КАНАЛЫ", "СТАТУС"])
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for index, width in [(1, 142), (2, 102), (3, 100)]:
            self.table.setColumnWidth(index, width)
        self.table.verticalHeader().setDefaultSectionSize(64)
        self.table.cellDoubleClicked.connect(lambda _row, _col: self.edit_selected())
        self.table.itemSelectionChanged.connect(self.update_actions)
        left.addWidget(self.table, 1)
        self.empty = QLabel("Пока пусто. Добавьте первую запись справа.", objectName="muted")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left.addWidget(self.empty)

        actions = QHBoxLayout()
        self.count_label = QLabel(objectName="muted")
        actions.addWidget(self.count_label)
        actions.addStretch()
        self.edit_button = QPushButton("Изменить")
        self.edit_button.clicked.connect(self.edit_selected)
        self.delete_button = QPushButton("Удалить", objectName="danger")
        self.delete_button.clicked.connect(self.delete_selected)
        actions.addWidget(self.edit_button)
        actions.addWidget(self.delete_button)
        left.addLayout(actions)
        content.addLayout(left, 1)

        editor = QFrame(objectName="editor")
        form_box = QVBoxLayout(editor)
        form_box.setContentsMargins(18, 18, 18, 18)
        form_box.setSpacing(8)
        form_box.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.form_heading = QLabel("Новая запись", objectName="section")
        form_box.addWidget(self.form_heading)
        form = QVBoxLayout()
        form.setSpacing(5)
        self.title_input = QLineEdit()
        self.title_input.setMaxLength(120)
        self.title_input.setPlaceholderText("Например, встреча с друзьями")
        form.addWidget(QLabel("Название"))
        form.addWidget(self.title_input)
        date_time = QHBoxLayout()
        self.date_input = QDateEdit()
        self.date_input.setCalendarPopup(True)
        self.date_input.setDisplayFormat("dd.MM.yyyy")
        self.date_input.setDateRange(QDate(1900, 1, 1), QDate(2199, 12, 31))
        self.time_input = QTimeEdit()
        self.time_input.setDisplayFormat("HH:mm")
        date_time.addWidget(self.date_input, 3)
        date_time.addWidget(self.time_input, 2)
        form.addWidget(QLabel("Дата и время"))
        form.addLayout(date_time)
        self.reminder_input = QComboBox()
        for label, minutes in [("В момент события", 0), ("За 5 минут", 5), ("За 15 минут", 15),
                               ("За 30 минут", 30), ("За 1 час", 60), ("За 1 день", 1440)]:
            self.reminder_input.addItem(label, minutes)
        form.addWidget(QLabel("Напомнить"))
        form.addWidget(self.reminder_input)
        self.notes_input = QTextEdit()
        self.notes_input.setAcceptRichText(False)
        self.notes_input.setPlaceholderText("Детали, адрес или небольшой план…")
        self.notes_input.setFixedHeight(68)
        form.addWidget(QLabel("Заметка"))
        form.addWidget(self.notes_input)
        form_box.addLayout(form)
        self.birthday_input = QCheckBox("День рождения · каждый год")
        form_box.addWidget(self.birthday_input)
        birthday_hint = QLabel("Дни рождения сохраняются при очистке.", objectName="muted")
        birthday_hint.setWordWrap(True)
        form_box.addWidget(birthday_hint)
        self.birthday_panel = QWidget()
        birthday_fields = QVBoxLayout(self.birthday_panel)
        birthday_fields.setContentsMargins(0, 0, 0, 0)
        birthday_fields.setSpacing(5)
        birthday_fields.addWidget(QLabel("Имя именинника"))
        self.birthday_name_input = QLineEdit()
        self.birthday_name_input.setObjectName("birthdayNameInput")
        self.birthday_name_input.setMaxLength(120)
        self.birthday_name_input.setPlaceholderText("Например, Алексей")
        birthday_fields.addWidget(self.birthday_name_input)
        birthday_fields.addWidget(QLabel("Год рождения · для расчёта возраста"))
        self.birth_year_input = QSpinBox()
        self.birth_year_input.setObjectName("birthdayBirthYear")
        self.birth_year_input.setRange(0, date.today().year)
        self.birth_year_input.setSpecialValueText("Не указан")
        birthday_fields.addWidget(self.birth_year_input)
        birthday_fields.addWidget(QLabel("Стиль поздравления в Telegram"))
        self.greeting_style_input = QComboBox()
        self.greeting_style_input.setObjectName("birthdayGreetingStyle")
        for key, label in STYLE_NAMES.items():
            self.greeting_style_input.addItem(label, key)
        self.greeting_style_input.setCurrentIndex(self.greeting_style_input.findData("funny"))
        self.greeting_style_input.setToolTip("Поздравление собирается из списков при отправке в Telegram. В уведомлении на ПК его нет.")
        birthday_fields.addWidget(self.greeting_style_input)
        self.birthday_preview = QLabel(objectName="banner")
        self.birthday_preview.setTextFormat(Qt.TextFormat.PlainText)
        self.birthday_preview.setWordWrap(True)
        birthday_fields.addWidget(self.birthday_preview)
        form_box.addWidget(self.birthday_panel)
        self.birthday_input.toggled.connect(self.update_birthday_preview)
        self.birthday_name_input.textChanged.connect(self.update_birthday_preview)
        self.birth_year_input.valueChanged.connect(self.update_birthday_preview)
        self.title_input.textChanged.connect(self.update_birthday_preview)
        self.date_input.dateChanged.connect(self.update_birthday_preview)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        form_box.addWidget(line)
        form_box.addWidget(QLabel("Уведомления"))
        self.system_input = QCheckBox("Всплывающее окно на компьютере")
        self.telegram_input = QCheckBox("В Telegram")
        self.telegram_input.setToolTip("Включите этот канал у записи и укажите API-ключ и ID чата / группы в настройках.")
        form_box.addWidget(self.system_input)
        form_box.addWidget(self.telegram_input)
        form_box.addStretch()
        self.save_button = QPushButton("Добавить запись", objectName="primary")
        self.save_button.clicked.connect(self.save_event)
        form_box.addWidget(self.save_button)
        self.cancel_button = QPushButton("Отменить редактирование")
        self.cancel_button.clicked.connect(self.new_event)
        form_box.addWidget(self.cancel_button)
        editor_scroll = QScrollArea()
        editor_scroll.setFixedWidth(340)
        editor_scroll.setWidgetResizable(True)
        editor_scroll.setFrameShape(QFrame.Shape.NoFrame)
        editor_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        editor_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        editor_scroll.setWidget(editor)
        content.addWidget(editor_scroll)
        outer.addLayout(content, 1)
        footer = QLabel("Уведомления работают, пока запущен Лист. Крестик сворачивает приложение в трей, если он доступен.", objectName="muted")
        footer.setWordWrap(True)
        outer.addWidget(footer)

    def stat_card(self, caption: str, value: str, accent: bool = False):
        card = QFrame(objectName="nextCard" if accent else "card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(17, 13, 17, 13)
        layout.setSpacing(4)
        layout.addWidget(QLabel(caption, objectName="eyebrow"))
        label = QLabel(value, objectName="statValue")
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        layout.addWidget(label)
        return label, card

    def build_tray(self) -> None:
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip("Лист — ежедневник")
        menu = QMenu(self)
        show_action = QAction("Открыть ежедневник", self)
        show_action.triggered.connect(self.restore_window)
        exit_action = QAction("Завершить работу", self)
        exit_action.triggered.connect(self.exit_app)
        menu.addAction(show_action)
        settings_action = QAction("Настройки", self)
        settings_action.triggered.connect(self.show_settings)
        menu.addAction(settings_action)
        menu.addSeparator()
        menu.addAction(exit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.tray_activated)
        self.tray.messageClicked.connect(self.restore_window)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def show_settings(self) -> None:
        self.restore_window()
        dialog = QDialog(self)
        dialog.setObjectName("settingsDialog")
        dialog.setWindowTitle("Настройки")
        dialog.setMinimumWidth(500)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(14)
        tabs = QTabWidget()
        tabs.setObjectName("settingsTabs")
        appearance = QWidget()
        appearance_layout = QVBoxLayout(appearance)
        appearance_layout.setSpacing(12)
        appearance_layout.addWidget(QLabel("Оформление", objectName="section"))
        appearance_layout.addWidget(QLabel("Тема приложения"))
        picker = QComboBox()
        picker.setObjectName("themePicker")
        for key, label in THEME_NAMES.items():
            picker.addItem(label + (" · по умолчанию" if key == DEFAULT_THEME else ""), key)
        picker.setCurrentIndex(picker.findData(self.theme))
        appearance_layout.addWidget(picker)
        hint = QLabel("Тема применяется сразу после сохранения и запоминается для следующих запусков.", objectName="muted")
        hint.setWordWrap(True)
        appearance_layout.addWidget(hint)
        appearance_layout.addStretch()
        tabs.addTab(appearance, "Оформление")

        telegram = QWidget()
        telegram_layout = QVBoxLayout(telegram)
        telegram_layout.setSpacing(12)
        telegram_layout.addWidget(QLabel("Телеграм-бот", objectName="section"))
        telegram_layout.addWidget(QLabel("API-ключ бота"))
        token_input = QLineEdit(self.repository.get_setting("telegram_bot_token"))
        token_input.setObjectName("telegramTokenInput")
        token_input.setEchoMode(QLineEdit.EchoMode.Password)
        token_input.setMaxLength(512)
        token_input.setPlaceholderText("Токен, полученный от BotFather")
        telegram_layout.addWidget(token_input)
        show_token = QCheckBox("Показать ключ")
        show_token.setObjectName("showTelegramToken")
        show_token.toggled.connect(lambda checked: token_input.setEchoMode(QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password))
        telegram_layout.addWidget(show_token)
        telegram_layout.addWidget(QLabel("ID чата / группы"))
        chat_input = QLineEdit(self.repository.get_setting("telegram_chat_id"))
        chat_input.setObjectName("telegramChatInput")
        chat_input.setMaxLength(128)
        chat_input.setPlaceholderText("Например: 123456789 или -1001234567890")
        telegram_layout.addWidget(chat_input)
        telegram_hint = QLabel("Для личного чата сначала нажмите /start у бота. Для группы добавьте бота и разрешите отправку сообщений. В самой записи включите «В Telegram».", objectName="muted")
        telegram_hint.setWordWrap(True)
        telegram_layout.addWidget(telegram_hint)
        test_button = QPushButton("Отправить тестовое сообщение")
        test_button.setObjectName("testTelegramButton")
        telegram_layout.addWidget(test_button)
        test_status = QLabel("Проверка отправит сообщение по введённым данным; сохранять настройки заранее не нужно.", objectName="muted")
        test_status.setObjectName("telegramTestStatus")
        test_status.setTextFormat(Qt.TextFormat.PlainText)
        test_status.setWordWrap(True)
        telegram_layout.addWidget(test_status)
        test_timer = QTimer(dialog)
        test_timer.setInterval(100)
        pending_test = {"ticket": None, "chat": ""}

        def poll_test() -> None:
            result = self.telegram_dispatcher.poll_test(pending_test["ticket"])
            if result is None:
                return
            test_timer.stop()
            test_button.setEnabled(True)
            test_status.setText(f"Тестовое сообщение отправлено в чат {pending_test['chat']}." if result.success else result.error)

        def test_telegram() -> None:
            settings = TelegramSettings(token_input.text().strip(), chat_input.text().strip())
            try:
                validate_settings(settings.bot_token, settings.chat_id)
            except TelegramError as exc:
                test_status.setText(str(exc))
                return
            ticket = self.telegram_dispatcher.start_test(settings)
            if ticket is None:
                test_status.setText("Предыдущая проверка ещё выполняется. Попробуйте через несколько секунд.")
                return
            pending_test.update(ticket=ticket, chat=settings.chat_id)
            test_button.setEnabled(False)
            test_status.setText("Отправляю сообщение…")
            test_timer.start()

        test_timer.timeout.connect(poll_test)
        test_button.clicked.connect(test_telegram)
        dialog.finished.connect(lambda _result: test_timer.stop())
        telegram_layout.addStretch()
        tabs.addTab(telegram, "Телеграм-бот")
        layout.addWidget(tabs)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Сохранить")
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("primary")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.rejected.connect(dialog.reject)

        def save_settings() -> None:
            bot_token = token_input.text().strip()
            chat_id = chat_input.text().strip()
            if bool(bot_token) != bool(chat_id):
                tabs.setCurrentWidget(telegram)
                QMessageBox.warning(dialog, "Настройки Telegram", "Заполните API-ключ и ID чата / группы или очистите оба поля.")
                return
            if bot_token:
                try:
                    validate_settings(bot_token, chat_id)
                except TelegramError as exc:
                    tabs.setCurrentWidget(telegram)
                    QMessageBox.warning(dialog, "Настройки Telegram", str(exc))
                    return
            try:
                self.repository.set_settings({
                    "theme": picker.currentData(),
                    "telegram_bot_token": bot_token,
                    "telegram_chat_id": chat_id,
                })
            except sqlite3.Error as exc:
                QMessageBox.warning(dialog, "Не удалось сохранить настройки", str(exc))
                return
            self.theme = apply_theme(picker.currentData())
            self.telegram_dispatcher.reconfigure(TelegramSettings(bot_token, chat_id))
            self.refresh()
            dialog.accept()
            self.telegram_tick()

        buttons.accepted.connect(save_settings)
        layout.addWidget(buttons)
        dialog.exec()

    def restore_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def update_birthday_preview(self, *_args) -> None:
        self.birthday_panel.setVisible(self.birthday_input.isChecked())
        if not self.birthday_input.isChecked():
            return
        event = Event("День рождения", self.date_input.date().toPython(), datetime.min.time(), is_birthday=True)
        occurrence = event.next_date(date.today())
        details = [f"Ближайший день рождения: {occurrence:%d.%m.%Y}"]
        year = self.birth_year_input.value()
        details.append(age_summary(occurrence.year - year) if year else "Год рождения не указан")
        self.birthday_preview.setText("\n".join(details))

    def tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.restore_window()

    def show_notification(self, title: str, body: str) -> None:
        self.banner.setText(title + " — " + body.replace("\n", " · "))
        self.banner.setToolTip(body)
        if self.reminder_popup is None:
            popup = ReminderPopup()
            popup.setWindowIcon(self.windowIcon())
            popup.open_planner.connect(self.restore_window)
            popup.finished.connect(lambda _result: self.clear_popup(popup))
            self.reminder_popup = popup
        self.reminder_popup.add_message(title, body)
        self.statusBar().showMessage("Напоминание открыто отдельным окном поверх других окон.", 15000)

    def clear_popup(self, popup: ReminderPopup) -> None:
        if self.reminder_popup is popup:
            self.reminder_popup = None

    def selected_id(self) -> int | None:
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def update_actions(self) -> None:
        selected = self.selected_id() is not None
        self.edit_button.setEnabled(selected)
        self.delete_button.setEnabled(selected)

    def refresh(self, *_args) -> None:
        today = date.today()
        now = datetime.now()
        days = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
        self.date_label.setText(f"{days[today.weekday()]}, {today:%d.%m.%Y}   ·   Всё важное — в одном месте")
        events = self.repository.all_events()
        self.today_value.setText(str(sum(event.next_date(today) == today for event in events)))
        future = [event for event in events if datetime.combine(event.next_date(today), event.event_time) >= now]
        # После сегодняшнего дня рождения ближайшее повторение — в следующем году.
        future += [event for event in events if event.is_birthday and event.next_date(today) == today
                   and datetime.combine(today, event.event_time) < now]
        def future_date(event):
            day = event.next_date(today)
            return event.occurrence_in(today.year + 1) if event.is_birthday and datetime.combine(day, event.event_time) < now else day
        future.sort(key=lambda event: (future_date(event), event.event_time))
        if future:
            event = future[0]
            title = event.title if len(event.title) < 35 else event.title[:32] + "…"
            self.next_value.setText(f"{title}\n{future_date(event):%d.%m} · {event.event_time:%H:%M}")
        else:
            self.next_value.setText("Пока нет планов")
        next_cleanup = self.repository.next_cleanup()
        self.cleanup_value.setText(next_cleanup.strftime("%d.%m.%Y") if next_cleanup else "При запуске")
        self.cleanup_value.setToolTip("Удаляются обычные записи с датой раньше дня очистки. Дни рождения остаются.")
        query = self.search.text().strip().casefold()
        mode = self.filter.currentIndex()
        shown = []
        for event in events:
            day = event.next_date(today)
            if query and query not in (event.title + " " + event.notes).casefold():
                continue
            if mode == 1 and day != today:
                continue
            if mode == 2 and day < today:
                continue
            if mode == 3 and not event.is_birthday:
                continue
            if mode == 4 and (event.is_birthday or day >= today):
                continue
            shown.append(event)
        shown.sort(key=lambda event: (event.next_date(today) < today, event.next_date(today), event.event_time))
        selected = self.selected_id()
        self.table.setRowCount(0)
        for event in shown:
            row = self.table.rowCount()
            self.table.insertRow(row)
            occurrence = event.next_date(today)
            status = "Прошло" if occurrence < today else "Сегодня" if occurrence == today else "Впереди"
            if self.repository.was_delivered(event.id, occurrence, "system"):
                status = "Напомнили"
            telegram_error = self.telegram_dispatcher.errors.get((event.id, occurrence), "")
            if event.notify_telegram:
                if self.repository.was_delivered(event.id, occurrence, "telegram"):
                    status = "TG: отправлено"
                elif telegram_error:
                    status = "TG: ошибка"
                elif not self.telegram_notifier.available:
                    status = "TG: настройка"
            channels = []
            if event.notify_system:
                channels.append("Система")
            if event.notify_telegram:
                channels.append("TG")
            title = ("ДР · " if event.is_birthday else "") + event.title
            if event.is_birthday and event.birth_year is not None:
                title += " · " + age_text(occurrence.year - event.birth_year)
            cells = [title, f"{occurrence:%d.%m.%Y}  {event.event_time:%H:%M}", " · ".join(channels) or "—", status]
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, event.id)
                item.setToolTip(event.notes if column == 0 else "Telegram: API-ключ и чат / группа задаются в настройках." if column == 2 else telegram_error or text)
                if column == 3:
                    item.setForeground(QColor(THEMES[self.theme]["danger" if telegram_error else "overdue" if status == "Прошло" else "upcoming"]))
                self.table.setItem(row, column, item)
            if event.id == selected:
                self.table.selectRow(row)
        self.empty.setVisible(not shown)
        self.empty.setText("Ничего не найдено. Измените поиск или фильтр." if events else "Пока пусто. Добавьте первую запись справа.")
        self.count_label.setText(f"Показано: {len(shown)} из {len(events)}")
        self.update_actions()

    def new_event(self) -> None:
        self.editing_id = None
        self.form_heading.setText("Новая запись")
        self.save_button.setText("Добавить запись")
        self.cancel_button.hide()
        self.title_input.clear()
        self.notes_input.clear()
        proposed = QDateTime.currentDateTime().addSecs(3600)
        self.date_input.setDate(proposed.date())
        self.time_input.setTime(proposed.time())
        self.reminder_input.setCurrentIndex(0)
        self.birthday_input.setChecked(False)
        self.birthday_name_input.clear()
        self.birth_year_input.setValue(0)
        self.greeting_style_input.setCurrentIndex(self.greeting_style_input.findData("funny"))
        self.update_birthday_preview()
        self.system_input.setChecked(True)
        self.telegram_input.setChecked(False)
        self.title_input.setFocus()

    def edit_selected(self) -> None:
        event_id = self.selected_id()
        event = self.repository.get(event_id) if event_id is not None else None
        if event is None:
            return
        self.editing_id = event.id
        self.form_heading.setText("Редактирование")
        self.save_button.setText("Сохранить изменения")
        self.cancel_button.show()
        self.title_input.setText(event.title)
        self.notes_input.setPlainText(event.notes)
        self.date_input.setDate(QDate(event.event_date.year, event.event_date.month, event.event_date.day))
        from PySide6.QtCore import QTime
        self.time_input.setTime(QTime(event.event_time.hour, event.event_time.minute))
        self.reminder_input.setCurrentIndex(max(0, self.reminder_input.findData(event.remind_minutes)))
        self.birthday_input.setChecked(event.is_birthday)
        self.birthday_name_input.setText(event.birthday_name)
        self.birth_year_input.setValue(event.birth_year or 0)
        self.greeting_style_input.setCurrentIndex(self.greeting_style_input.findData(event.greeting_style))
        self.update_birthday_preview()
        self.system_input.setChecked(event.notify_system)
        self.telegram_input.setChecked(event.notify_telegram)

    def save_event(self) -> None:
        event = Event(
            id=self.editing_id, title=self.title_input.text(), notes=self.notes_input.toPlainText(),
            event_date=self.date_input.date().toPython(), event_time=self.time_input.time().toPython().replace(second=0, microsecond=0),
            is_birthday=self.birthday_input.isChecked(), remind_minutes=self.reminder_input.currentData(),
            notify_system=self.system_input.isChecked(), notify_telegram=self.telegram_input.isChecked(),
            birthday_name=self.birthday_name_input.text().strip() if self.birthday_input.isChecked() else "",
            birth_year=(self.birth_year_input.value() or None) if self.birthday_input.isChecked() else None,
            greeting_style=self.greeting_style_input.currentData(),
        )
        try:
            self.repository.save(event)
        except (ValueError, sqlite3.Error) as exc:
            QMessageBox.warning(self, "Не удалось сохранить", str(exc))
            return
        self.new_event()
        self.refresh()
        self.banner.setText("Запись сохранена." + (" Укажите API-ключ и чат / группу в настройках Telegram." if event.notify_telegram and not self.telegram_notifier.available else ""))
        self.tick()

    def delete_selected(self) -> None:
        event_id = self.selected_id()
        event = self.repository.get(event_id) if event_id is not None else None
        if event is None:
            return
        answer = QMessageBox.question(self, "Удалить запись?", f"Удалить «{event.title}»?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.repository.delete(event.id)
        if self.editing_id == event.id:
            self.new_event()
        self.refresh()

    def tick(self) -> None:
        if not self.timer.isActive():
            return
        try:
            removed, delivered = self.scheduler.tick()
            today = date.today()
            if removed is not None or delivered or today != self.last_date:
                self.refresh()
                self.last_date = today
            if removed:
                if self.editing_id is not None and self.repository.get(self.editing_id) is None:
                    self.new_event()
                self.statusBar().showMessage(f"Плановая очистка: удалено старых записей — {removed}. Дни рождения сохранены.", 20000)
            self.telegram_tick()
        except sqlite3.Error:
            logging.getLogger(__name__).exception("Ошибка базы при проверке напоминаний")
            self.banner.setText("Не удалось проверить напоминания. Проверьте доступ к файлу базы; повтор через 10 секунд.")

    def telegram_tick(self) -> None:
        try:
            delivered, error = self.telegram_dispatcher.tick()
            if delivered or error:
                self.refresh()
                if error:
                    self.banner.setText("Telegram: " + error)
                else:
                    self.banner.setText("Напоминание отправлено в Telegram.")
        except sqlite3.Error:
            self.banner.setText("Не удалось сохранить результат отправки Telegram. Проверьте доступ к базе.")

    def shutdown_background(self) -> None:
        self.telegram_timer.stop()
        self.telegram_dispatcher.close()

    def exit_app(self) -> None:
        self.exit_requested = True
        self.timer.stop()
        self.shutdown_background()
        self.tray.hide()
        if self.reminder_popup is not None:
            self.reminder_popup.close()
        QApplication.instance().quit()

    def closeEvent(self, event) -> None:
        if not self.exit_requested and QSystemTrayIcon.isSystemTrayAvailable():
            self.hide()
            event.ignore()
            if not self.tray_hint_shown:
                self.tray_hint_shown = True
                self.tray.showMessage("Лист работает в фоне", "Откройте окно через значок в трее. Для выхода выберите «Завершить работу».")
        else:
            self.timer.stop()
            self.shutdown_background()
            if self.reminder_popup is not None:
                self.reminder_popup.close()
            event.accept()


def seed_demo(repository: Repository) -> None:
    """Только по явному --demo и только для пустой базы."""
    if repository.all_events():
        return
    now = datetime.now()
    samples = [
        Event("Спланировать неделю", (now + timedelta(hours=1)).date(), (now + timedelta(hours=1)).time().replace(second=0, microsecond=0), "Выбрать три главные задачи и освободить время для отдыха.", notify_system=False),
        Event("День рождения Саши", now.date() + timedelta(days=2), datetime.strptime("10:00", "%H:%M").time(), "Позвонить и поздравить. Не забыть про подарок!", is_birthday=True, remind_minutes=1440, notify_system=False),
        Event("Забрать заказ", now.date() + timedelta(days=1), datetime.strptime("18:30", "%H:%M").time(), "Пункт выдачи рядом с домом.", remind_minutes=30, notify_system=False),
        Event("Встреча с друзьями", now.date() + timedelta(days=4), datetime.strptime("19:00", "%H:%M").time(), "Забронировать столик на четверых.", notify_system=False, notify_telegram=True),
    ]
    for event in samples:
        repository.save(event)
