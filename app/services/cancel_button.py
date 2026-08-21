"""Keeps at most one live "❌ Отменить" button on screen per application, instead
of stacking a fresh copy under every interview question. A wall of identical
cancel buttons (one per question, none ever cleared) reads as the bot nagging
the user to cancel — this clears the previous one before showing a new one,
which still satisfies "available at every step" (TZ v1.1 p.29) without piling up."""

from __future__ import annotations

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, Message

from app.db.repo import Repo


async def send_with_single_cancel_button(
    bot: Bot, repo: Repo, application: dict, chat_id: int, text: str, reply_markup: InlineKeyboardMarkup
) -> Message:
    old_message_id = application.get("last_cancel_message_id")
    if old_message_id:
        try:
            await bot.edit_message_reply_markup(chat_id=chat_id, message_id=old_message_id, reply_markup=None)
        except Exception:
            pass  # message may already be edited/gone/too old — cosmetic only, not worth failing over

    sent = await bot.send_message(chat_id, text, reply_markup=reply_markup)
    await repo.applications.set_last_cancel_message_id(application["id"], sent.message_id)
    return sent


async def clear_cancel_button(bot: Bot, repo: Repo, application: dict, chat_id: int) -> None:
    old_message_id = application.get("last_cancel_message_id")
    if not old_message_id:
        return
    try:
        await bot.edit_message_reply_markup(chat_id=chat_id, message_id=old_message_id, reply_markup=None)
    except Exception:
        pass
    await repo.applications.set_last_cancel_message_id(application["id"], None)
