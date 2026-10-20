"""HTTPS-клиент Telegram Bot API без дополнительных зависимостей."""
from __future__ import annotations

import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class TelegramError(Exception):
    """Только безопасный текст: URL и токен в исключение не включаются."""

    def __init__(self, message: str, retry_after: int = 60):
        super().__init__(message)
        self.retry_after = max(1, min(retry_after, 86400))


def validate_settings(bot_token: str, chat_id: str) -> None:
    if not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]+", bot_token):
        raise TelegramError("Неверный формат API-ключа. Скопируйте токен бота целиком из BotFather.")
    if not re.fullmatch(r"-?[0-9]+|@[A-Za-z0-9_]+", chat_id) or chat_id == "0":
        raise TelegramError("Укажите числовой ID чата / группы или @имя публичной группы / канала.")


def _api_error(payload: dict, fallback_code: int = 0) -> TelegramError:
    code = payload.get("error_code", fallback_code)
    description = str(payload.get("description", "")).lower()
    parameters = payload.get("parameters")
    parameters = parameters if isinstance(parameters, dict) else {}
    migrated = parameters.get("migrate_to_chat_id")
    if isinstance(migrated, int):
        return TelegramError(f"У группы изменился ID. Укажите в настройках: {migrated}.")
    if code in (401, 404):
        return TelegramError("Telegram не принял API-ключ. Проверьте токен бота в настройках.")
    if code == 403:
        return TelegramError("Бот не может писать в чат. Нажмите /start в личном чате с ботом или добавьте его в группу с правом отправки сообщений.")
    if code == 429:
        seconds = parameters.get("retry_after", 60)
        seconds = seconds if isinstance(seconds, int) and not isinstance(seconds, bool) else 60
        error = TelegramError("Telegram ограничил частоту запросов.", seconds)
        error.args = (f"Telegram ограничил частоту запросов. Повтор через {error.retry_after} сек.",)
        return error
    if code == 400 and "chat not found" in description:
        return TelegramError("Чат не найден. Проверьте ID; откройте личный чат с ботом и нажмите /start либо добавьте бота в группу.")
    if code == 400:
        return TelegramError("Telegram отклонил запрос. Проверьте ID чата / группы и права бота.")
    return TelegramError("Ошибка сервиса Telegram. Отправка будет повторена позже.")


def send_message(bot_token: str, chat_id: str, text: str, *, timeout: float = 15) -> None:
    """Возвращается только после подтверждения sendMessage. Может вызвать TelegramError."""
    bot_token, chat_id = bot_token.strip(), chat_id.strip()
    validate_settings(bot_token, chat_id)
    if not text.strip() or len(text) > 4096:
        raise TelegramError("Сообщение должно содержать от 1 до 4096 символов. Сократите текст и повторите отправку.")
    request = Request(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        data=json.dumps({"chat_id": chat_id, "text": text}, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"}, method="POST",
    )
    failure_code = 0
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(65537)
    except HTTPError as exc:
        failure_code = exc.code
        try:
            raw = exc.read(65537)
        except Exception:
            raise _api_error({}, failure_code) from None
        finally:
            exc.close()
    except (URLError, OSError, TimeoutError):
        raise TelegramError("Нет связи с Telegram. Проверьте интернет и доступ к api.telegram.org.") from None
    try:
        if len(raw) > 65536:
            raise ValueError("Response too large")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("Expected an object")
    except (ValueError, UnicodeError):
        if failure_code:
            raise _api_error({}, failure_code) from None
        raise TelegramError("Telegram вернул некорректный ответ. Попробуйте ещё раз.") from None
    if failure_code or payload.get("ok") is not True:
        raise _api_error(payload, failure_code)
    if not isinstance(payload.get("result"), dict) or not isinstance(payload["result"].get("message_id"), int):
        raise TelegramError("Telegram не подтвердил отправку сообщения. Попробуйте ещё раз.")
