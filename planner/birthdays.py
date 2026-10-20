"""Возраст, юбилеи и сообщения для интерфейса и обоих каналов уведомлений."""
from __future__ import annotations

from datetime import date
import re


def plural(number: int, one: str, few: str, many: str) -> str:
    number = abs(number)
    if 11 <= number % 100 <= 14:
        return many
    if number % 10 == 1:
        return one
    if 2 <= number % 10 <= 4:
        return few
    return many


def age_text(age: int) -> str:
    if age < 0:
        raise ValueError("Год рождения не может быть позже года поздравления.")
    return f"{age} {plural(age, 'год', 'года', 'лет')}"


def age_summary(age: int) -> str:
    years = age_text(age)
    if age == 18:
        return years + " — совершеннолетие"
    if age >= 20 and age % 5 == 0:
        return years + " — юбилей"
    return years


def get_birthday_message(name: str, birth_year: int | None, current_year: int | None = None,
                         *, when: str = "сегодня") -> str:
    year = date.today().year if current_year is None else current_year
    name = name.strip() or "Именинник"
    if birth_year is None:
        return f"🎂 {name}: {when} день рождения! Самое время подготовить поздравление."
    age = year - birth_year
    years = age_text(age)
    match age:
        case 18:
            return f"🎉 {name}: {when} совершеннолетие! Исполняется 18 лет! 🔞"
        case value if value >= 20 and value % 5 == 0:
            return f"✨ {name}: {when} юбилей! Исполняется {years}! 🥂"
        case _:
            return f"🎂 {name}: {when} день рождения! Исполняется {years}!"


def birthday_when(occurrence: date, today: date | None = None) -> str:
    days = (occurrence - (today or date.today())).days
    if days == 0:
        return "сегодня"
    if days == 1:
        return "завтра"
    if days > 1:
        return f"через {days} {plural(days, 'день', 'дня', 'дней')}"
    return f"{occurrence:%d.%m.%Y}"


def person_from_title(title: str) -> str:
    person = re.sub(r"^(?:день\s+рождения|д\.?\s*р\.?)[\s:·—-]*", "", title.strip(), flags=re.IGNORECASE)
    return person.strip() or title.strip()
