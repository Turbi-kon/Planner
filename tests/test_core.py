from dataclasses import replace
from datetime import date, datetime, time, timedelta
from pathlib import Path
import tempfile
import unittest

from planner.database import Repository
from planner.models import Event, add_months
from planner.notifications import TelegramNotifier, TelegramSettings
from planner.scheduler import Scheduler


class FakeNotifier:
    name = "system"
    available = True

    def __init__(self):
        self.calls = []
        self.success = True
        self.error = False

    def send(self, event, occurrence):
        self.calls.append((event.id, occurrence))
        if self.error:
            raise RuntimeError("delivery failure")
        return self.success


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "planner.sqlite3"
        self.repo = Repository(self.path)
        self.now = datetime(2026, 10, 19, 12, 0)
        self.repo.cleanup_if_due(self.now.date())

    def tearDown(self):
        self.repo.close()
        self.directory.cleanup()

    def event(self, **changes):
        return self.repo.save(replace(Event("Встреча", self.now.date(), time(12)), **changes))

    def test_save_update_restart_and_delete(self):
        event = self.event(title="  Встреча  ", notes="Адрес")
        self.assertEqual(self.repo.get(event.id).title, "Встреча")
        self.repo.save(replace(event, title="Новое название", notify_telegram=True))
        self.repo.close()
        self.repo = Repository(self.path)
        saved = self.repo.get(event.id)
        self.assertEqual(saved.title, "Новое название")
        self.assertTrue(saved.notify_telegram)
        self.repo.delete(event.id)
        self.assertEqual(self.repo.all_events(), [])

    def test_empty_title_is_rejected(self):
        with self.assertRaises(ValueError):
            self.event(title="   ")

    def test_sql_text_is_stored_as_data(self):
        title = "'); DROP TABLE events; --"
        self.event(title=title)
        self.assertEqual(self.repo.all_events()[0].title, title)

    def test_cleanup_preserves_today_future_and_birthdays(self):
        old = self.event(event_date=date(2025, 1, 1))
        today = self.event(event_date=date(2027, 4, 19))
        future = self.event(event_date=date(2027, 4, 20))
        birthday = self.event(event_date=date(1999, 1, 1), is_birthday=True)
        self.repo.mark_delivered(old.id, old.event_date, "system", self.now)
        self.assertIsNone(self.repo.cleanup_if_due(date(2027, 4, 18)))
        self.assertEqual(self.repo.cleanup_if_due(date(2027, 4, 19)), 1)
        self.assertEqual({e.id for e in self.repo.all_events()}, {today.id, future.id, birthday.id})
        self.assertFalse(self.repo.was_delivered(old.id, old.event_date, "system"))
        self.assertEqual(self.repo.next_cleanup(), date(2027, 10, 19))

    def test_first_cleanup_and_missed_schedule(self):
        self.repo.connection.execute("DELETE FROM app_settings")
        self.event(event_date=date(2025, 1, 1))
        self.assertEqual(self.repo.cleanup_if_due(self.now.date()), 1)
        self.assertIsNone(self.repo.cleanup_if_due(self.now.date()))
        self.assertEqual(self.repo.cleanup_if_due(date(2028, 2, 29)), 0)
        self.assertEqual(self.repo.next_cleanup(), date(2028, 8, 29))

    def test_delivery_is_unique_and_survives_restart(self):
        event = self.event()
        channel = FakeNotifier()
        Scheduler(self.repo, [channel]).tick(self.now)
        self.repo.close()
        self.repo = Repository(self.path)
        Scheduler(self.repo, [channel]).tick(self.now + timedelta(minutes=1))
        self.assertEqual(channel.calls, [(event.id, event.event_date)])

    def test_notification_channels_are_independent(self):
        event = self.event(notify_telegram=True)
        channel = FakeNotifier()
        Scheduler(self.repo, [channel, TelegramNotifier()]).tick(self.now)
        self.assertTrue(self.repo.was_delivered(event.id, event.event_date, "system"))
        self.assertFalse(self.repo.was_delivered(event.id, event.event_date, "telegram"))

    def test_failure_retries_after_a_minute(self):
        event = self.event()
        channel = FakeNotifier()
        channel.success = False
        scheduler = Scheduler(self.repo, [channel])
        scheduler.tick(self.now)
        self.assertFalse(self.repo.was_delivered(event.id, event.event_date, "system"))
        channel.success = True
        scheduler.tick(self.now + timedelta(seconds=20))
        self.assertEqual(len(channel.calls), 1)
        scheduler.tick(self.now + timedelta(minutes=1))
        self.assertEqual(len(channel.calls), 2)
        self.assertTrue(self.repo.was_delivered(event.id, event.event_date, "system"))

    def test_exception_does_not_mark_as_sent(self):
        event = self.event()
        channel = FakeNotifier()
        channel.error = True
        with self.assertLogs("planner.scheduler", level="WARNING"):
            Scheduler(self.repo, [channel]).tick(self.now)
        self.assertFalse(self.repo.was_delivered(event.id, event.event_date, "system"))

    def test_schedule_change_resets_delivery_but_note_change_does_not(self):
        event = self.event()
        self.repo.mark_delivered(event.id, event.event_date, "system", self.now)
        edited = replace(event, notes="Уточнение")
        self.repo.save(edited)
        self.assertTrue(self.repo.was_delivered(event.id, event.event_date, "system"))
        self.repo.save(replace(edited, event_time=time(15)))
        self.assertFalse(self.repo.was_delivered(event.id, event.event_date, "system"))

    def test_early_and_disabled_notifications_are_not_sent(self):
        self.event(event_time=time(13))
        self.event(notify_system=False)
        channel = FakeNotifier()
        self.assertEqual(Scheduler(self.repo, [channel]).tick(self.now)[1], 0)
        self.assertEqual(channel.calls, [])

    def test_multiple_due_notifications_are_spaced_without_loss(self):
        self.event(title="Первая")
        self.event(title="Вторая")
        channel = FakeNotifier()
        scheduler = Scheduler(self.repo, [channel])
        self.assertEqual(scheduler.tick(self.now)[1], 1)
        self.assertEqual(scheduler.tick(self.now + timedelta(seconds=10))[1], 1)
        self.assertEqual(scheduler.tick(self.now + timedelta(seconds=20))[1], 0)
        self.assertEqual(len(channel.calls), 2)

    def test_birthday_reminds_again_next_year(self):
        event = self.event(event_date=date(1990, 10, 19), is_birthday=True)
        channel = FakeNotifier()
        scheduler = Scheduler(self.repo, [channel])
        scheduler.tick(self.now)
        scheduler.tick(datetime(2027, 10, 19, 12))
        self.assertEqual(channel.calls, [(event.id, date(2026, 10, 19)), (event.id, date(2027, 10, 19))])
        self.assertIsNotNone(self.repo.get(event.id))

    def test_newer_database_is_not_downgraded(self):
        self.repo.connection.execute("PRAGMA user_version = 5")
        with self.assertRaisesRegex(RuntimeError, "новой версией"):
            Repository(self.path)

    def test_telegram_preferences_survive_restart(self):
        self.repo.set_settings({"telegram_bot_token": "example-not-a-real-token", "telegram_chat_id": "-1001234567890", "theme": "dark"})
        self.repo.close()
        self.repo = Repository(self.path)
        config = TelegramSettings(self.repo.get_setting("telegram_bot_token"), self.repo.get_setting("telegram_chat_id"))
        self.assertTrue(config.configured)
        self.assertEqual(config.chat_id, "-1001234567890")
        self.assertNotIn(config.bot_token, repr(config))
        self.assertTrue(TelegramNotifier(config).available)
        self.assertEqual(self.repo.get_setting("theme"), "dark")


class CalendarTests(unittest.TestCase):
    def test_six_calendar_months(self):
        self.assertEqual(add_months(date(2026, 8, 31), 6), date(2027, 2, 28))
        self.assertEqual(add_months(date(2027, 8, 31), 6), date(2028, 2, 29))

    def test_leap_day_birthday(self):
        event = Event("День рождения", date(2000, 2, 29), time(10), is_birthday=True)
        self.assertEqual(event.next_date(date(2027, 1, 1)), date(2027, 2, 28))
        self.assertEqual(event.next_date(date(2027, 3, 1)), date(2028, 2, 29))

    def test_new_year_advance_reminder(self):
        event = Event("День рождения", date(1990, 1, 1), time(10), is_birthday=True, remind_minutes=1440)
        self.assertEqual(event.due_occurrences(datetime(2026, 12, 31, 10)), [date(2027, 1, 1)])

    def test_no_catchup_for_past_birthdays(self):
        event = Event("День рождения", date(1990, 4, 1), time(10), is_birthday=True)
        self.assertEqual(event.due_occurrences(datetime(2026, 10, 19, 12)), [])

    def test_normal_advance_reminder(self):
        event = Event("Встреча", date(2026, 10, 20), time(10), remind_minutes=60)
        self.assertEqual(event.due_occurrences(datetime(2026, 10, 20, 8, 59)), [])
        self.assertEqual(event.due_occurrences(datetime(2026, 10, 20, 9)), [date(2026, 10, 20)])


if __name__ == "__main__":
    unittest.main()
