"""/help — opens the standalone Telegra.ph page, no AI/state involved (TZ v1.1 p.4, p.27)."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot import texts

router = Router(name="help")


@router.message(Command("help"))
async def cmd_help(message: Message, is_admin: bool, telegraph_help_url: str) -> None:
    if is_admin:
        return
    if telegraph_help_url:
        await message.answer(f"Подробное описание сервиса: {telegraph_help_url}")
    else:
        await message.answer(texts.HELP_FALLBACK)
