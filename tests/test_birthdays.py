from dataclasses import replace
from datetime import date, time
from pathlib import Path
import random
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from planner.birthdays import age_text, birthday_when, get_birthday_message
from planner.database import Repository
from planner.greetings import BANKS, GreetingParts, compose_greeting, random_parts
from planner.models import Event
from planner.notifications import message_for, telegram_text_for


class BirthdayMessageTests(unittest.TestCase):
    def test_russian_age_declension_including_teens_and_hundreds(self):
        examples = {0: "0 лет", 1: "1 год", 2: "2 года", 4: "4 года", 5: "5 лет", 11: "11 лет",
                    12: "12 лет", 14: "14 лет", 18: "18 лет", 21: "21 год", 23: "23 года",
                    25: "25 лет", 94: "94 года", 101: "101 год", 111: "111 лет", 122: "122 года"}
        for age, expected in examples.items():
            with self.subTest(age=age):
                self.assertEqual(age_text(age), expected)

    def test_requested_examples_and_adulthood(self):
        self.assertIn("юбилей", get_birthday_message("Алексей", 2001, 2026))
        self.assertIn("25 лет", get_birthday_message("Алексей", 2001, 2026))
        self.assertIn("23 года", get_birthday_message("Мария", 2003, 2026))
        self.assertIn("21 год", get_birthday_message("Иван", 2005, 2026))
        self.assertIn("совершеннолетие", get_birthday_message("Именинник", 2008, 2026))
        self.assertIn("юбилей", get_birthday_message("Именинник", 1926, 2026))

    def test_year_is_not_fixed_to_2026(self):
        self.assertIn("26 лет", get_birthday_message("Алексей", 2001, 2027))
        self.assertIn("20 лет", get_birthday_message("Алексей", date.today().year - 20))

    def test_unknown_year_and_negative_age(self):
        self.assertIn("день рождения", get_birthday_message("Алексей", None, 2026))
        self.assertNotIn("лет", get_birthday_message("Алексей", None, 2026))
        with self.assertRaises(ValueError):
            get_birthday_message("Алексей", 2030, 2026)

    def test_advance_reminder_does_not_say_today(self):
        event = Event("День рождения Алексея", date(2026, 1, 1), time(10), is_birthday=True,
                      birthday_name="Алексей", birth_year=2002)
        with patch("planner.notifications.random_parts") as generate:
            _, body = message_for(event, date(2027, 1, 1), today=date(2026, 12, 31))
            generate.assert_not_called()
        self.assertEqual(body, "01.01.2027 в 10:00")
        self.assertNotIn("юбилей", body)
        self.assertNotIn("25 лет", body)
        self.assertNotIn("сегодня", body)
        self.assertEqual(birthday_when(date(2026, 10, 24), date(2026, 10, 20)), "через 4 дня")

    def test_greeting_is_not_cut_to_old_350_character_limit(self):
        event = Event("Праздник", date(2026, 10, 20), time(10), notes="П" * 600)
        self.assertIn(event.notes, message_for(event, event.event_date)[1])

    def test_ordinary_telegram_message_has_requested_three_parts(self):
        event = Event("Встреча", date(2026, 10, 20), time(10, 30), notes="Взять документы\nПозвонить заранее")
        self.assertEqual(telegram_text_for(event, event.event_date), "Встреча\n20.10.2026 10:30\nВзять документы\nПозвонить заранее")

    def test_birthday_message_has_name_date_optional_age_and_generated_text(self):
        parts = GreetingParts("от всей души", "поздравляю!", "Желаю счастья.", "И отдыха.", "С праздником!")
        event = Event("Поздравить Алексея", date(2026, 10, 20), time(10, 30), notes="Купить подарок",
                      is_birthday=True, birthday_name="Алексей", birth_year=2001, greeting_style="warm")
        with patch("planner.notifications.random_parts", return_value=parts) as generate:
            text = telegram_text_for(event, event.event_date)
            generate.assert_called_once_with("warm")
        self.assertTrue(text.startswith("Алексей\n20.10.2026 10:30\n25 лет — юбилей\nОт всей души поздравляю!"))
        self.assertNotIn("Купить подарок", text)
        self.assertNotIn(event.title, text)
        with patch("planner.notifications.random_parts", return_value=parts):
            unknown = telegram_text_for(replace(event, birth_year=None), event.event_date)
        self.assertTrue(unknown.startswith("Алексей\n20.10.2026 10:30\nОт всей души"))
        self.assertNotIn("25 лет", unknown)


class GreetingTests(unittest.TestCase):
    def test_every_style_builds_complete_coherent_blocks(self):
        for style, bank in BANKS.items():
            with self.subTest(style=style):
                parts = random_parts(style, random.Random(42))
                text = compose_greeting("Алексей", parts, 2001, 2026)
                self.assertTrue(text.startswith("Алексей, "))
                self.assertIn("юбилей — 25 лет", text)
                self.assertIn(parts.ending, text)
                for key, choices in bank.items():
                    self.assertIn(getattr(parts, key), choices)

    def test_optional_name_year_and_explicit_year(self):
        parts = random_parts("warm", random.Random(1))
        text = compose_greeting("", parts)
        self.assertTrue(text[0].isupper())
        self.assertNotIn("Сегодня тебе", text)
        self.assertNotIn("{", text)
        self.assertIn("совершеннолетием", compose_greeting("Алексей", parts, 2008, 2026))
        with self.assertRaises(ValueError):
            compose_greeting("Алексей", parts, 2030, 2026)


class BirthdayDatabaseTests(unittest.TestCase):
    def test_birthday_metadata_survives_restart_and_update(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "planner.sqlite3"
            repo = Repository(path)
            event = repo.save(Event("Поздравить Алексея", date(2026, 12, 1), time(10), is_birthday=True,
                                    birthday_name="Алексей", birth_year=2001, greeting_style="developer"))
            repo.close()
            repo = Repository(path)
            self.assertEqual(repo.get(event.id).birthday_name, "Алексей")
            self.assertEqual(repo.get(event.id).birth_year, 2001)
            self.assertEqual(repo.get(event.id).greeting_style, "developer")
            repo.save(replace(repo.get(event.id), birth_year=2000, birthday_name="Александр"))
            self.assertEqual(repo.get(event.id).birth_year, 2000)
            repo.close()

    def test_upgrade_v1_preserves_records_deliveries_and_settings(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "old.sqlite3"
            connection = sqlite3.connect(path)
            schema = (Path(__file__).parents[1] / "planner" / "schema.sql").read_text(encoding="utf-8")
            new_fields = ("birthday_name ", "birth_year ", "telegram_text ", "greeting_style ")
            old_schema = "\n".join(line for line in schema.splitlines() if not line.lstrip().startswith(new_fields))
            old_schema = old_schema.replace("PRAGMA user_version = 4;", "PRAGMA user_version = 1;")
            connection.executescript(old_schema)
            connection.execute("INSERT INTO events (title,event_date,event_time,is_birthday,created_at,updated_at) VALUES ('День рождения','1990-01-01','10:00',1,'2026-01-01','2026-01-01')")
            connection.execute("INSERT INTO notification_deliveries (event_id,occurrence_date,channel,delivered_at) VALUES (1,'2026-01-01','system','2026-01-01')")
            connection.execute("INSERT INTO app_settings (key,value) VALUES ('theme','dark')")
            connection.commit()
            connection.close()
            repo = Repository(path)
            self.assertEqual(repo.get(1).title, "День рождения")
            self.assertIsNone(repo.get(1).birth_year)
            self.assertEqual(repo.get_setting("theme"), "dark")
            self.assertTrue(repo.was_delivered(1, date(2026, 1, 1), "system"))
            self.assertEqual(repo.connection.execute("PRAGMA user_version").fetchone()[0], 4)
            self.assertEqual(repo.get(1).greeting_style, "funny")
            repo.close()

    def test_old_custom_text_is_preserved_but_not_used_for_sending(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "planner.sqlite3"
            schema = (Path(__file__).parents[1] / "planner" / "schema.sql").read_text(encoding="utf-8")
            old_schema = "\n".join(line for line in schema.splitlines() if not line.lstrip().startswith("greeting_style "))
            connection = sqlite3.connect(path)
            connection.executescript(old_schema.replace("PRAGMA user_version = 4;", "PRAGMA user_version = 3;"))
            connection.execute("INSERT INTO events (title,notes,event_date,event_time,telegram_text,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
                               ("Название", "Текст заметки", "2026-10-20", "10:00", "Старый отдельный текст", "2026-10-20", "2026-10-20"))
            connection.commit()
            connection.close()
            repo = Repository(path)
            event = repo.get(1)
            self.assertEqual(event.greeting_style, "funny")
            self.assertEqual(repo.connection.execute("PRAGMA user_version").fetchone()[0], 4)
            loaded = repo.get(event.id)
            repo.save(replace(loaded, title="Новое название"))
            self.assertEqual(telegram_text_for(repo.get(event.id), event.event_date), "Новое название\n20.10.2026 10:00\nТекст заметки")
            self.assertEqual(repo.connection.execute("SELECT telegram_text FROM events WHERE id=?", (event.id,)).fetchone()[0], "Старый отдельный текст")
            repo.close()


if __name__ == "__main__":
    unittest.main()
