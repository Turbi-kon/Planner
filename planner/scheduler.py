from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from .database import Repository
from .notifications import Notifier

logger = logging.getLogger(__name__)


class Scheduler:
    def __init__(self, repository: Repository, channels: list[Notifier]):
        self.repository = repository
        self.channels = channels
        self.retry_after: dict[tuple[int, date, str], datetime] = {}

    def tick(self, now: datetime | None = None) -> tuple[int | None, int]:
        now = now or datetime.now()
        removed = self.repository.cleanup_if_due(now.date())
        delivered = 0
        sent_channels: set[str] = set()
        self.retry_after = {key: value for key, value in self.retry_after.items() if value > now}
        for event in self.repository.all_events():
            for occurrence in event.due_occurrences(now):
                for channel in self.channels:
                    enabled = event.notify_system if channel.name == "system" else event.notify_telegram
                    if not enabled or not channel.available:
                        continue
                    # Разносим напоминания одного канала по тикам (10 секунд),
                    # не перегружая окно и не теряя остальные события.
                    if channel.name in sent_channels:
                        continue
                    key = (event.id, occurrence, channel.name)
                    if key in self.retry_after or self.repository.was_delivered(*key):
                        continue
                    try:
                        success = channel.send(event, occurrence)
                    except Exception:
                        # Не выводим исключение адаптера: в нём может оказаться токен.
                        logger.warning("Не удалось передать уведомление: канал %s, запись %s", channel.name, event.id)
                        success = False
                    if success:
                        self.repository.mark_delivered(event.id, occurrence, channel.name, now)
                        delivered += 1
                        sent_channels.add(channel.name)
                    else:
                        self.retry_after[key] = now + timedelta(minutes=1)
        return removed, delivered
