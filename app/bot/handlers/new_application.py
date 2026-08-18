"""/new, "Создать заявку"/"Создать новую" and cancel buttons (TZ v1.1 p.25, p.29)."""

from __future__ import annotations

from typing import Awaitable, Callable

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.bot import keyboards, texts
from app.bot.keyboards import CB_CANCEL_PREFIX, CB_CREATE_APPLICATION
from app.constants import TERMINAL_STATES
from app.db.repo import Repo
from app.services.application_flow import ApplicationFlowService
from app.services.locks import LockRegistry

router = Router(name="new_application")


async def _start_new_application_flow(
    user: dict, repo: Repo, flow: ApplicationFlowService, send: Callable[..., Awaitable[Message]]
) -> None:
    incomplete = await repo.applications.get_incomplete_for_user(user["id"])
    if incomplete:
        await send(
            "У вас уже есть незавершённая заявка. Продолжите её или отмените, прежде чем начинать новую.",
            reply_markup=keyboards.incomplete_session_keyboard(incomplete["id"]),
        )
        return

    application = await flow.create_application(user)
    await send(texts.INITIAL_DESCRIPTION_PROMPT, reply_markup=keyboards.question_keyboard(application["id"]))


@router.message(Command("new"))
async def cmd_new(message: Message, user: dict | None, is_admin: bool, repo: Repo, flow: ApplicationFlowService) -> None:
    if is_admin or user is None:
        return
    await _start_new_application_flow(user, repo, flow, message.answer)


@router.callback_query(F.data == CB_CREATE_APPLICATION)
async def cb_create_application(
    callback: CallbackQuery, user: dict | None, repo: Repo, flow: ApplicationFlowService
) -> None:
    if user is None:
        await callback.answer()
        return
    await callback.message.edit_reply_markup(reply_markup=None)
    await _start_new_application_flow(user, repo, flow, callback.message.answer)
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CB_CANCEL_PREFIX}:"))
async def cb_cancel_application(
    callback: CallbackQuery, user: dict | None, repo: Repo, flow: ApplicationFlowService, lock_registry: LockRegistry
) -> None:
    if user is None:
        await callback.answer()
        return

    application_id = int(callback.data.split(":")[1])
    async with lock_registry.get(user["id"], application_id):
        application = await repo.applications.get(application_id)
        if application is None or application["user_id"] != user["id"]:
            await callback.answer()
            return
        if application["state"] in TERMINAL_STATES:
            await callback.message.edit_reply_markup(reply_markup=None)
            await callback.answer()
            return

        await flow.cancel_application(application)
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(texts.CANCEL_CONFIRMATION)
        await callback.answer()
