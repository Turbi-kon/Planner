"""Рабочий поток выполняет HTTP; SQLite читается и меняется только главным потоком."""
from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Callable

from .database import Repository
from .models import Event
from .notifications import TelegramNotifier, TelegramSettings, telegram_text_for
from .telegram_api import TelegramError, send_message


@dataclass(frozen=True)
class SendResult:
    success: bool
    error: str = ""
    retry_after: int = 60


@dataclass(frozen=True)
class PendingSend:
    event: Event
    occurrence: date
    settings: TelegramSettings = field(repr=False)
    future: Future = field(repr=False)
    generation: int = 0


def schedule_of(event: Event) -> tuple:
    return (event.event_date, event.event_time, event.is_birthday, event.remind_minutes,
            event.title, event.notes, event.birthday_name, event.birth_year, event.greeting_style)


class TelegramDispatcher:
    def __init__(self, repository: Repository, notifier: TelegramNotifier,
                 sender: Callable[[str, str, str], None] | None = None):
        self.repository = repository
        self.notifier = notifier
        self.sender = sender or send_message
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="telegram")
        self.pending: PendingSend | None = None
        self.test_future: Future | None = None
        self.test_ticket = 0
        self.generation = 0
        self.cooldown_until = datetime.min
        self.errors: dict[tuple[int, date], str] = {}
        self.closed = False

    def _send(self, settings: TelegramSettings, text: str) -> SendResult:
        try:
            self.sender(settings.bot_token, settings.chat_id, text)
            return SendResult(True)
        except TelegramError as exc:
            return SendResult(False, str(exc), exc.retry_after)
        except Exception:
            
            return SendResult(False, "Не удалось отправить сообщение в Telegram. Проверьте настройки и соединение.")

    def _send_event(self, settings: TelegramSettings, event: Event, occurrence: date) -> SendResult:
        # Генерация выполняется рабочим потоком непосредственно перед HTTP,
        # а не при сохранении записи, предпросмотре или показе окна на ПК.
        try:
            text = telegram_text_for(event, occurrence)
        except Exception:
            return SendResult(False, "Не удалось подготовить сообщение Telegram. Проверьте данные записи.")
        return self._send(settings, text)

    def reconfigure(self, settings: TelegramSettings) -> None:
        if settings != self.notifier.settings:
            self.generation += 1
            self.notifier.settings = settings
            self.errors.clear()
            self.cooldown_until = datetime.min

    def tick(self, now: datetime | None = None) -> tuple[int, str]:
        if self.closed:
            return 0, ""
        now = now or datetime.now()
        delivered, error = 0, ""
        if self.pending is not None:
            job = self.pending
            if not job.future.done():
                return 0, ""
            result = job.future.result()
            current = self.repository.get(job.event.id)
            # Не записываем успех для удалённой/перенесённой записи или новых настроек.
            applicable = (current is not None and current.notify_telegram
                          and schedule_of(current) == schedule_of(job.event)
                          and self.generation == job.generation
                          and self.notifier.settings == job.settings)
            if applicable:
                key = (job.event.id, job.occurrence)
                if result.success:
                    self.repository.mark_delivered(*key, "telegram", now)
                    self.errors.pop(key, None)
                    delivered = 1
                else:
                    self.errors[key] = error = result.error
                    self.cooldown_until = now + timedelta(seconds=result.retry_after)
            self.pending = None
        if not self.notifier.available or now < self.cooldown_until:
            return delivered, error
        if self.test_future is not None and not self.test_future.done():
            return delivered, error
        events = self.repository.all_events()
        existing = {event.id for event in events}
        self.errors = {key: value for key, value in self.errors.items() if key[0] in existing}
        for event in sorted(events, key=lambda item: (item.next_date(now.date()), item.event_time)):
            if not event.notify_telegram:
                continue
            for occurrence in event.due_occurrences(now):
                if self.repository.was_delivered(event.id, occurrence, "telegram"):
                    continue
                settings = self.notifier.settings
                future = self.executor.submit(self._send_event, settings, event, occurrence)
                self.pending = PendingSend(event, occurrence, settings, future, self.generation)
                return delivered, error
        return delivered, error

    def start_test(self, settings: TelegramSettings) -> int | None:
        if self.closed or self.test_future is not None and not self.test_future.done():
            return None
        self.test_ticket += 1
        self.test_future = self.executor.submit(self._send, settings, "Лист: проверка уведомлений. Бот подключён, сообщения приходят.")
        return self.test_ticket

    def poll_test(self, ticket: int) -> SendResult | None:
        if ticket != self.test_ticket or self.test_future is None or not self.test_future.done():
            return None
        result = self.test_future.result()
        self.test_future = None
        return result

    def close(self) -> None:
        self.closed = True
        self.executor.shutdown(wait=False, cancel_futures=True)
