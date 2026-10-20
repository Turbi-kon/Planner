"""Каналы уведомлений. Синхронный Telegram-клиент вызывается из рабочего потока."""
from __future__ import annotations

from datetime import date
from dataclasses import dataclass, field
from typing import Callable, Protocol

from .models import Event
from .birthdays import age_summary, person_from_title
from .greetings import compose_greeting, random_parts
from .telegram_api import send_message


class Notifier(Protocol):
    name: str
    available: bool

    def send(self, event: Event, occurrence: date) -> bool: ...


def message_for(event: Event, occurrence: date, *, today: date | None = None) -> tuple[str, str]:
    title = ("День рождения · " if event.is_birthday else "Напоминание · ") + event.title
    body = f"{occurrence:%d.%m.%Y} в {event.event_time:%H:%M}"
    if event.notes:
        body += "\n" + event.notes[:3000] + ("…" if len(event.notes) > 3000 else "")
    return title, body


def telegram_text_for(event: Event, occurrence: date) -> str:
    stamp = f"{occurrence:%d.%m.%Y} {event.event_time:%H:%M}"
    if not event.is_birthday:
        return f"{event.title}\n{stamp}\n{event.notes}"
    person = event.birthday_name.strip() or person_from_title(event.title) or "Именинник"
    lines = [person, stamp]
    if event.birth_year is not None:
        lines.append(age_summary(occurrence.year - event.birth_year))
    # Возраст и имя уже находятся в строках выше. Заметка сюда не добавляется.
    greeting = compose_greeting("", random_parts(event.greeting_style))
    return "\n".join([*lines, greeting])


class SystemNotifier:
    name = "system"
    available = True

    def __init__(self, show: Callable[[str, str], None]):
        self.show = show

    def send(self, event: Event, occurrence: date) -> bool:
        self.show(*message_for(event, occurrence))
        return True


@dataclass(frozen=True)
class TelegramSettings:
    bot_token: str = field(default="", repr=False)
    chat_id: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.bot_token.strip() and self.chat_id.strip())


class TelegramNotifier:
    """Отправка через sendMessage. GUI использует TelegramDispatcher для работы в фоне."""

    name = "telegram"

    def __init__(self, settings: TelegramSettings | None = None):
        self.settings = settings or TelegramSettings()

    @property
    def available(self) -> bool:
        return self.settings.configured

    def send(self, event: Event, occurrence: date) -> bool:
        send_message(self.settings.bot_token, self.settings.chat_id, telegram_text_for(event, occurrence))
        return True
