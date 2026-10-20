from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import date, datetime, time
from pathlib import Path

from .models import Event, add_months


class Repository:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, timeout=10)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        if version > 4:
            self.connection.close()
            raise RuntimeError("База создана более новой версией ежедневника.")
        self.connection.execute("PRAGMA journal_mode = WAL")
        # Безопасное обновление существующей базы v1: записи и доставки сохраняются.
        columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(events)")}
        if columns:
            with self.connection:
                if "birthday_name" not in columns:
                    self.connection.execute("ALTER TABLE events ADD COLUMN birthday_name TEXT NOT NULL DEFAULT ''")
                if "birth_year" not in columns:
                    self.connection.execute("ALTER TABLE events ADD COLUMN birth_year INTEGER CHECK(birth_year IS NULL OR birth_year BETWEEN 1 AND 9999)")
                if "telegram_text" not in columns:
                    self.connection.execute("ALTER TABLE events ADD COLUMN telegram_text TEXT NOT NULL DEFAULT ''")
                if "greeting_style" not in columns:
                    self.connection.execute("ALTER TABLE events ADD COLUMN greeting_style TEXT NOT NULL DEFAULT 'funny' CHECK(greeting_style IN ('warm', 'funny', 'developer'))")
        self.connection.executescript(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))

    def close(self) -> None:
        self.connection.close()

    def get_setting(self, key: str, default: str = "") -> str:
        row = self.connection.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.set_settings({key: value})

    def set_settings(self, values: dict[str, str]) -> None:
        """Сохраняет вкладки настроек одной транзакцией."""
        with self.connection:
            self.connection.executemany("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", values.items())

    @staticmethod
    def _event(row: sqlite3.Row) -> Event:
        return Event(
            id=row["id"], title=row["title"], notes=row["notes"],
            event_date=date.fromisoformat(row["event_date"]),
            event_time=time.fromisoformat(row["event_time"]),
            is_birthday=bool(row["is_birthday"]), remind_minutes=row["remind_minutes"],
            notify_system=bool(row["notify_system"]), notify_telegram=bool(row["notify_telegram"]),
            birthday_name=row["birthday_name"], birth_year=row["birth_year"],
            greeting_style=row["greeting_style"],
        )

    def all_events(self) -> list[Event]:
        return [self._event(row) for row in self.connection.execute("SELECT * FROM events")]

    def get(self, event_id: int) -> Event | None:
        row = self.connection.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        return self._event(row) if row else None

    def save(self, event: Event) -> Event:
        event.validate()
        stamp = datetime.now().isoformat(timespec="seconds")
        values = (
            event.title.strip(), event.notes.strip(), event.event_date.isoformat(),
            event.event_time.strftime("%H:%M"), int(event.is_birthday), event.remind_minutes,
            int(event.notify_system), int(event.notify_telegram), event.birthday_name.strip(), event.birth_year, event.greeting_style, stamp,
        )
        with self.connection:
            if event.id is None:
                cursor = self.connection.execute(
                    """INSERT INTO events (title, notes, event_date, event_time, is_birthday,
                    remind_minutes, notify_system, notify_telegram, birthday_name, birth_year, greeting_style, updated_at, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", values + (stamp,),
                )
                return replace(event, id=cursor.lastrowid, title=event.title.strip())
            previous = self.get(event.id)
            if previous is None:
                raise ValueError("Запись уже удалена.")
            self.connection.execute(
                """UPDATE events SET title=?, notes=?, event_date=?, event_time=?, is_birthday=?,
                remind_minutes=?, notify_system=?, notify_telegram=?, birthday_name=?, birth_year=?, greeting_style=?, updated_at=? WHERE id=?""",
                values + (event.id,),
            )
            schedule = lambda item: (item.event_date, item.event_time, item.is_birthday, item.remind_minutes)
            if schedule(previous) != schedule(event):
                self.connection.execute("DELETE FROM notification_deliveries WHERE event_id=?", (event.id,))
        return event

    def delete(self, event_id: int) -> None:
        with self.connection:
            self.connection.execute("DELETE FROM events WHERE id=?", (event_id,))

    def was_delivered(self, event_id: int, occurrence: date, channel: str) -> bool:
        return self.connection.execute(
            "SELECT 1 FROM notification_deliveries WHERE event_id=? AND occurrence_date=? AND channel=?",
            (event_id, occurrence.isoformat(), channel),
        ).fetchone() is not None

    def mark_delivered(self, event_id: int, occurrence: date, channel: str, now: datetime) -> None:
        with self.connection:
            self.connection.execute(
                """INSERT OR IGNORE INTO notification_deliveries
                (event_id, occurrence_date, channel, delivered_at) VALUES (?, ?, ?, ?)""",
                (event_id, occurrence.isoformat(), channel, now.isoformat(timespec="seconds")),
            )

    def next_cleanup(self) -> date | None:
        row = self.connection.execute("SELECT value FROM app_settings WHERE key='next_cleanup_on'").fetchone()
        return date.fromisoformat(row[0]) if row else None

    def cleanup_if_due(self, today: date) -> int | None:
        """Первый запуск и затем каждые шесть календарных месяцев.

        None означает, что срок ещё не наступил; 0 — проверка была, удалять нечего.
        Удаление и перенос срока выполняются одной транзакцией.
        """
        next_run = self.next_cleanup()
        if next_run is not None and today < next_run:
            return None
        with self.connection:
            cursor = self.connection.execute(
                "DELETE FROM events WHERE is_birthday=0 AND event_date < ?", (today.isoformat(),),
            )
            self.connection.execute(
                "INSERT OR REPLACE INTO app_settings (key, value) VALUES ('next_cleanup_on', ?)",
                (add_months(today, 6).isoformat(),),
            )
            self.connection.execute(
                "INSERT OR REPLACE INTO app_settings (key, value) VALUES ('last_cleanup_on', ?)",
                (today.isoformat(),),
            )
        return cursor.rowcount
