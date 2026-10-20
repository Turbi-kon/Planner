-- Создаётся автоматически. Даты: YYYY-MM-DD, время: HH:MM (местное время ПК).
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 120),
    notes TEXT NOT NULL DEFAULT '',
    event_date TEXT NOT NULL,
    event_time TEXT NOT NULL,
    is_birthday INTEGER NOT NULL DEFAULT 0 CHECK(is_birthday IN (0, 1)),
    remind_minutes INTEGER NOT NULL DEFAULT 0 CHECK(remind_minutes >= 0),
    notify_system INTEGER NOT NULL DEFAULT 1 CHECK(notify_system IN (0, 1)),
    notify_telegram INTEGER NOT NULL DEFAULT 0 CHECK(notify_telegram IN (0, 1)),
    birthday_name TEXT NOT NULL DEFAULT '',
    birth_year INTEGER CHECK(birth_year IS NULL OR birth_year BETWEEN 1 AND 9999),
    telegram_text TEXT NOT NULL DEFAULT '', -- Не используется; сохранено для совместимости со старыми базами.
    greeting_style TEXT NOT NULL DEFAULT 'funny' CHECK(greeting_style IN ('warm', 'funny', 'developer')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- По одной отправке для каждого события, ежегодного повторения и канала.
CREATE TABLE IF NOT EXISTS notification_deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    occurrence_date TEXT NOT NULL,
    channel TEXT NOT NULL CHECK(channel IN ('system', 'telegram')),
    delivered_at TEXT NOT NULL,
    UNIQUE(event_id, occurrence_date, channel)
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_date ON events(event_date);
CREATE INDEX IF NOT EXISTS idx_deliveries_event ON notification_deliveries(event_id);
PRAGMA user_version = 4;
