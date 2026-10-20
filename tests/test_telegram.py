from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from io import BytesIO
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from planner.database import Repository
from planner.models import Event
from planner.notifications import TelegramNotifier, TelegramSettings, message_for
from planner.greetings import GreetingParts
from planner.telegram_api import TelegramError, send_message
from planner.telegram_dispatcher import TelegramDispatcher


TOKEN = "123456789:example_token_for_tests_only"
CHAT = "-1001234567890"


@contextmanager
def response(payload):
    yield BytesIO(json.dumps(payload).encode("utf-8"))


class TelegramApiTests(unittest.TestCase):
    @patch("planner.telegram_api.urlopen")
    def test_post_json_with_unicode_and_acknowledgement(self, open_url):
        open_url.return_value = response({"ok": True, "result": {"message_id": 42}})
        send_message(TOKEN, CHAT, "Напоминание <без HTML>")
        request = open_url.call_args.args[0]
        self.assertEqual(request.full_url, f"https://api.telegram.org/bot{TOKEN}/sendMessage")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(json.loads(request.data), {"chat_id": CHAT, "text": "Напоминание <без HTML>"})
        self.assertEqual(open_url.call_args.kwargs["timeout"], 15)

    @patch("planner.telegram_api.urlopen")
    def test_invalid_credentials_never_reach_network(self, open_url):
        for token, chat in [("", CHAT), ("not-a-token", CHAT), (TOKEN, "https://somewhere"), (TOKEN, "0")]:
            with self.subTest(token_valid=token == TOKEN, chat=chat):
                with self.assertRaises(TelegramError):
                    send_message(token, chat, "test")
        open_url.assert_not_called()

    @patch("planner.telegram_api.urlopen")
    def test_http_errors_are_safe_and_explained(self, open_url):
        for code, description, expected in [(401, "Unauthorized", "API-ключ"),
                                             (400, "Bad Request: chat not found", "Чат не найден"),
                                             (403, "Forbidden", "Бот не может"),
                                             (500, TOKEN, "Ошибка сервиса")]:
            with self.subTest(code=code):
                body = json.dumps({"ok": False, "error_code": code, "description": description}).encode()
                open_url.side_effect = HTTPError(f"https://example/{TOKEN}", code, TOKEN, None, BytesIO(body))
                with self.assertRaises(TelegramError) as caught:
                    send_message(TOKEN, CHAT, "test")
                self.assertIn(expected, str(caught.exception))
                self.assertNotIn(TOKEN, str(caught.exception))

    @patch("planner.telegram_api.urlopen")
    def test_rate_limit_uses_retry_after(self, open_url):
        open_url.return_value = response({"ok": False, "error_code": 429, "parameters": {"retry_after": 125}})
        with self.assertRaises(TelegramError) as caught:
            send_message(TOKEN, CHAT, "test")
        self.assertEqual(caught.exception.retry_after, 125)

    @patch("planner.telegram_api.urlopen")
    def test_timeout_and_bad_json_do_not_leak_url(self, open_url):
        for error in [URLError(f"https://example/{TOKEN}"), TimeoutError(TOKEN)]:
            open_url.side_effect = error
            with self.assertRaises(TelegramError) as caught:
                send_message(TOKEN, CHAT, "test")
            self.assertNotIn(TOKEN, str(caught.exception))
        open_url.side_effect = None
        open_url.return_value = BytesIO(b"not JSON")
        with self.assertRaises(TelegramError):
            send_message(TOKEN, CHAT, "test")

    @patch("planner.telegram_api.urlopen")
    def test_ok_without_message_is_not_success(self, open_url):
        open_url.return_value = response({"ok": True, "result": {}})
        with self.assertRaises(TelegramError):
            send_message(TOKEN, CHAT, "test")

    @patch("planner.telegram_api.urlopen")
    def test_long_or_empty_message_is_rejected_without_silent_truncation(self, open_url):
        for text in [" ", "x" * 4097]:
            with self.assertRaises(TelegramError):
                send_message(TOKEN, CHAT, text)
        open_url.assert_not_called()


class TelegramDispatcherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Repository(Path(self.temp.name) / "planner.sqlite3")
        self.now = datetime(2026, 10, 20, 12)
        self.repo.cleanup_if_due(self.now.date())
        self.notifier = TelegramNotifier(TelegramSettings(TOKEN, CHAT))
        self.dispatcher = TelegramDispatcher(self.repo, self.notifier, sender=lambda *_: None)
        self.gates = []

    def tearDown(self):
        for gate in self.gates:
            gate.set()
        self.dispatcher.close()
        self.dispatcher.executor.shutdown(wait=True)
        self.repo.close()
        self.temp.cleanup()

    def event(self, **changes):
        return self.repo.save(replace(Event("Встреча", self.now.date(), time(12), notify_telegram=True), **changes))

    def finish(self, now=None):
        self.dispatcher.pending.future.result(timeout=3)
        return self.dispatcher.tick(now or self.now)

    def test_async_request_only_marks_after_acknowledgement(self):
        event = self.event()
        gate = threading.Event()
        self.gates.append(gate)
        worker_threads = []
        def sender(*_):
            worker_threads.append(threading.get_ident())
            gate.wait(3)
        self.dispatcher.sender = sender
        self.assertEqual(self.dispatcher.tick(self.now), (0, ""))
        self.assertFalse(self.repo.was_delivered(event.id, event.event_date, "telegram"))
        gate.set()
        self.assertEqual(self.finish(), (1, ""))
        self.assertNotEqual(worker_threads[0], threading.get_ident())
        self.assertTrue(self.repo.was_delivered(event.id, event.event_date, "telegram"))
        self.assertEqual(self.dispatcher.tick(self.now)[0], 0)
        self.assertIsNone(self.dispatcher.pending)

    def test_api_failure_retries_and_respects_server_cooldown(self):
        event = self.event()
        def fail(*_):
            raise TelegramError("Ограничение запросов", 125)
        self.dispatcher.sender = fail
        self.dispatcher.tick(self.now)
        delivered, error = self.finish()
        self.assertEqual(delivered, 0)
        self.assertTrue(error)
        self.assertFalse(self.repo.was_delivered(event.id, event.event_date, "telegram"))
        self.dispatcher.tick(self.now + timedelta(seconds=124))
        self.assertIsNone(self.dispatcher.pending)
        self.dispatcher.sender = lambda *_: None
        self.dispatcher.tick(self.now + timedelta(seconds=125))
        self.assertEqual(self.finish(self.now + timedelta(seconds=126))[0], 1)

    def test_completed_request_cannot_mark_deleted_event(self):
        event = self.event()
        self.dispatcher.tick(self.now)
        self.repo.delete(event.id)
        self.assertEqual(self.finish(), (0, ""))

    def test_completed_request_cannot_mark_changed_schedule(self):
        event = self.event()
        self.dispatcher.tick(self.now)
        self.repo.save(replace(event, event_time=time(15)))
        self.assertEqual(self.finish(), (0, ""))
        self.assertFalse(self.repo.was_delivered(event.id, event.event_date, "telegram"))

    def test_reconfiguration_does_not_count_old_destination_as_new(self):
        event = self.event()
        calls = []
        self.dispatcher.sender = lambda token, chat, text: calls.append(chat)
        self.dispatcher.tick(self.now)
        self.dispatcher.pending.future.result(timeout=3)
        self.dispatcher.reconfigure(TelegramSettings(TOKEN, "123456"))
        self.assertEqual(self.dispatcher.tick(self.now)[0], 0)
        self.assertFalse(self.repo.was_delivered(event.id, event.event_date, "telegram"))
        self.assertEqual(self.finish()[0], 1)
        self.assertEqual(calls, [CHAT, "123456"])

    def test_test_message_does_not_change_event_delivery(self):
        event = self.event()
        ticket = self.dispatcher.start_test(TelegramSettings(TOKEN, CHAT))
        self.dispatcher.test_future.result(timeout=3)
        self.assertTrue(self.dispatcher.poll_test(ticket).success)
        self.assertFalse(self.repo.was_delivered(event.id, event.event_date, "telegram"))

    def test_channel_choice_and_system_delivery_are_independent(self):
        ignored = self.event(notify_telegram=False)
        event = self.event()
        self.repo.mark_delivered(event.id, event.event_date, "system", self.now)
        self.dispatcher.tick(self.now)
        self.assertEqual(self.finish()[0], 1)
        self.assertFalse(self.repo.was_delivered(ignored.id, ignored.event_date, "telegram"))

    def test_database_error_keeps_successful_response_without_resending(self):
        from sqlite3 import OperationalError
        self.event()
        self.dispatcher.tick(self.now)
        self.dispatcher.pending.future.result(timeout=3)
        with patch.object(self.repo, "mark_delivered", side_effect=OperationalError("busy")):
            with self.assertRaises(OperationalError):
                self.dispatcher.tick(self.now)
        self.assertIsNotNone(self.dispatcher.pending)
        self.assertEqual(self.dispatcher.tick(self.now)[0], 1)

    def test_scheduled_send_uses_note_structure(self):
        captured = []
        self.dispatcher.sender = lambda token, chat, text: captured.append(text)
        event = self.event(notes="Текст заметки")
        self.dispatcher.tick(self.now)
        self.finish()
        self.assertEqual(captured, ["Встреча\n20.10.2026 12:00\nТекст заметки"])

    def test_greeting_is_generated_by_worker_just_before_send_and_never_for_pc(self):
        gate = threading.Event()
        self.gates.append(gate)
        self.dispatcher.executor.submit(gate.wait, 3)
        captured, generation_threads = [], []
        parts = GreetingParts("от души", "поздравляю!", "Счастья.", "Здоровья.", "С праздником!")
        def generate(style):
            generation_threads.append(threading.get_ident())
            self.assertEqual(style, "developer")
            return parts
        self.dispatcher.sender = lambda token, chat, text: captured.append(text)
        with patch("planner.notifications.random_parts", side_effect=generate) as generator:
            event = self.event(is_birthday=True, birthday_name="Алексей", birth_year=2001, greeting_style="developer")
            self.dispatcher.tick(self.now)
            pc_title, pc_body = message_for(event, event.event_date)
            generator.assert_not_called()
            self.assertNotIn("поздравляю", pc_body)
            gate.set()
            self.finish()
            generator.assert_called_once()
        self.assertNotEqual(generation_threads[0], threading.get_ident())
        self.assertTrue(captured[0].startswith("Алексей\n20.10.2026 12:00\n25 лет — юбилей\nОт души поздравляю!"))


if __name__ == "__main__":
    unittest.main()
