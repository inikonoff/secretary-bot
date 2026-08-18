"""Single, unobtrusive reminder for incomplete sessions (TZ v1.1 p.55). Runs as a
background poll loop — exactly one reminder per application, tracked via
applications.reminder_sent_at so a restart never re-sends it."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from app.constants import EVENT_REMINDER_SENT
from app.db.repo import Repo

logger = logging.getLogger(__name__)

REMINDER_TEXT = (
    "Вы начали оформлять заявку, но не закончили. Если хотите продолжить — просто "
    "напишите сообщение здесь, я вернусь к тому же месту. Если передумали — заявку "
    "можно отменить кнопкой «❌ Отменить заявку» через /new."
)

POLL_INTERVAL_SECONDS = 900  # 15 minutes is enough resolution for a "reminder_hours"-scale timeout.


async def reminder_loop(bot: Bot, repo: Repo, reminder_hours: float) -> None:
    while True:
        try:
            stale = await repo.applications.list_stale_incomplete(reminder_hours)
            for application in stale:
                try:
                    await bot.send_message(application["telegram_id"], REMINDER_TEXT)
                    await repo.applications.mark_reminder_sent(application["id"])
                    await repo.events.log(
                        EVENT_REMINDER_SENT, application_id=application["id"], user_id=application["user_id"]
                    )
                except Exception:
                    logger.exception("failed to send reminder for application_id=%s", application["id"])
        except Exception:
            logger.exception("reminder loop iteration failed")

        await asyncio.sleep(POLL_INTERVAL_SECONDS)
