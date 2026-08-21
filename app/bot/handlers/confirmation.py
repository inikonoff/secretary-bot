""""✅ Верно" / "➕ Добавить информацию" (TZ v1.1 p.12-15, p.30-31, p.44)."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from app.bot import keyboards, texts
from app.bot.keyboards import CB_ADD_INFO_PREFIX, CB_CONFIRM_OK_PREFIX
from app.constants import STATE_ADDING_INFORMATION, STATE_FINALIZING, STATE_WAITING_CONFIRMATION
from app.db.repo import Repo
from app.services.application_flow import ApplicationFlowService
from app.services.cancel_button import send_with_single_cancel_button
from app.services.locks import LockRegistry
from app.services.tz_generator import TZGenerationError, TZGeneratorService

router = Router(name="confirmation")

ADD_INFO_PROMPT = "Хорошо, дополните описание текстом или голосом — что ещё важно учесть?"

FINALIZATION_FAILED_MESSAGE = (
    "Не получилось сформировать заявку из-за временной ошибки сервиса. Пожалуйста, "
    "нажмите «✅ Верно» ещё раз через пару минут."
)


@router.callback_query(F.data.startswith(f"{CB_ADD_INFO_PREFIX}:"))
async def cb_add_info(
    callback: CallbackQuery, user: dict | None, repo: Repo, flow: ApplicationFlowService, lock_registry: LockRegistry
) -> None:
    if user is None:
        await callback.answer()
        return

    application_id = int(callback.data.split(":")[1])
    async with lock_registry.get(user["id"], application_id):
        application = await repo.applications.get(application_id)
        if application is None or application["user_id"] != user["id"] or application["state"] != STATE_WAITING_CONFIRMATION:
            await callback.answer()
            return
        if not flow.can_add_information(application):
            await callback.answer()
            return

        await callback.message.edit_reply_markup(reply_markup=None)
        await repo.applications.increment_add_info_count(application_id)
        await repo.applications.update_state(application_id, STATE_ADDING_INFORMATION)
        application["last_cancel_message_id"] = None  # just cleared above
        await send_with_single_cancel_button(
            callback.bot, repo, application, callback.message.chat.id, ADD_INFO_PROMPT,
            keyboards.question_keyboard(application_id),
        )
        await callback.answer()


@router.callback_query(F.data.startswith(f"{CB_CONFIRM_OK_PREFIX}:"))
async def cb_confirm_ok(
    callback: CallbackQuery,
    user: dict | None,
    repo: Repo,
    lock_registry: LockRegistry,
    tz_generator: TZGeneratorService,
    bot: Bot,
    admin_id: int,
) -> None:
    if user is None:
        await callback.answer()
        return

    application_id = int(callback.data.split(":")[1])
    async with lock_registry.get(user["id"], application_id):
        application = await repo.applications.get(application_id)
        if application is None or application["user_id"] != user["id"] or application["state"] != STATE_WAITING_CONFIRMATION:
            await callback.answer()
            return

        await callback.message.edit_reply_markup(reply_markup=None)
        await repo.applications.update_state(application_id, STATE_FINALIZING)
        await callback.answer()

        try:
            await tz_generator.generate_and_finalize(application)
        except TZGenerationError:
            await repo.applications.update_state(application_id, STATE_WAITING_CONFIRMATION)
            application["last_cancel_message_id"] = None  # cleared above
            await send_with_single_cancel_button(
                callback.bot, repo, application, callback.message.chat.id, FINALIZATION_FAILED_MESSAGE,
                keyboards.question_keyboard(application_id),
            )
            return

        await callback.message.answer(texts.FINAL_CONFIRMATION_TO_CLIENT)

        open_button = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📋 Открыть заявку", callback_data=f"adm:app:{application_id}")
        ]])
        client = await repo.users.get_client_card(application["user_id"])
        client_label = f"@{client['username']}" if client and client.get("username") else f"id{application['user_id']}"
        await bot.send_message(
            admin_id,
            f"🆕 Новая заявка от {client_label}\nЗаявка #{application_id}",
            reply_markup=open_button,
        )
