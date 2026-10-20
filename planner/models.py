from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta


def add_months(value: date, months: int) -> date:
    index = value.year * 12 + value.month - 1 + months
    year, month_index = divmod(index, 12)
    month = month_index + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


@dataclass(frozen=True)
class Event:
    title: str
    event_date: date
    event_time: time
    notes: str = ""
    is_birthday: bool = False
    remind_minutes: int = 0
    notify_system: bool = True
    notify_telegram: bool = False
    id: int | None = None
    birthday_name: str = ""
    birth_year: int | None = None
    greeting_style: str = "funny"

    def validate(self) -> None:
        if not 1 <= len(self.title.strip()) <= 120:
            raise ValueError("Название должно содержать от 1 до 120 символов.")
        if len(self.notes) > 5000:
            raise ValueError("Заметка должна быть не длиннее 5000 символов.")
        if not 0 <= self.remind_minutes <= 525600:
            raise ValueError("Недопустимый интервал напоминания.")
        if len(self.birthday_name.strip()) > 120:
            raise ValueError("Имя должно быть не длиннее 120 символов.")
        if self.birth_year is not None and (type(self.birth_year) is not int or not 1 <= self.birth_year <= date.today().year):
            raise ValueError("Укажите существующий год рождения или оставьте его неизвестным.")
        if self.greeting_style not in ("warm", "funny", "developer"):
            raise ValueError("Выберите стиль поздравления Telegram.")

    def occurrence_in(self, year: int) -> date:
        # День рождения 29 февраля в невисокосный год отмечаем 28 февраля.
        day = min(self.event_date.day, calendar.monthrange(year, self.event_date.month)[1])
        return date(year, self.event_date.month, day)

    def next_date(self, today: date) -> date:
        if not self.is_birthday:
            return self.event_date
        occurrence = self.occurrence_in(today.year)
        return occurrence if occurrence >= today else self.occurrence_in(today.year + 1)

    def reminder_at(self, occurrence: date) -> datetime:
        return datetime.combine(occurrence, self.event_time) - timedelta(minutes=self.remind_minutes)

    def due_occurrences(self, now: datetime) -> list[date]:
        if not self.is_birthday:
            return [self.event_date] if self.reminder_at(self.event_date) <= now else []
        # Прошлые дни рождения не догоняем. Учитываем заблаговременное
        # напоминание о январском дне рождения в декабре предыдущего года.
        candidates = [self.occurrence_in(year) for year in range(now.year, now.year + 3)]
        return [day for day in candidates if day >= now.date() and self.reminder_at(day) <= now]
