"""/start (TZ v1.1 p.4, p.26)."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.bot import keyboards, texts
from app.db.repo import Repo

router = Router(name="start")


def _incomplete_summary(application: dict) -> str:
    text = application.get("client_understanding_text") or application.get("pending_understanding_message")
    if text:
        return text
    return "заявка находится в процессе оформления."


@router.message(CommandStart())
async def cmd_start(message: Message, user: dict | None, is_admin: bool, repo: Repo) -> None:
    if is_admin:
        from app.bot.handlers.admin import send_admin_menu

        await send_admin_menu(message, repo)
        return

    if user is None:
        return

    incomplete = await repo.applications.get_incomplete_for_user(user["id"])
    if incomplete:
        await message.answer(
            "У вас есть незавершённая заявка. Вот на чём вы остановились:\n\n" + _incomplete_summary(incomplete),
            reply_markup=keyboards.incomplete_session_keyboard(incomplete["id"]),
        )
        return

    finalized = await repo.applications.list_finalized_for_user(user["id"])
    if finalized:
        await message.answer(
            "С возвращением! Хотите оформить новую заявку?",
            reply_markup=keyboards.new_application_only_keyboard(),
        )
    else:
        await message.answer(texts.GREETING, reply_markup=keyboards.create_application_keyboard())
