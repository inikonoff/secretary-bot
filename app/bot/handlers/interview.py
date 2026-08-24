"""Text/voice interview input, attachments, and post-finalization client<->admin
correspondence (TZ v1.1 p.6, p.18, p.20-22, p.28, p.49)."""

from __future__ import annotations

import logging
import re

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message

from app.ai.orchestrator import AIOrchestrator, AIUnavailableError
from app.bot import keyboards, texts
from app.bot.keyboards import CB_DEADLINE_QUICK_PREFIX, DEADLINE_QUICK_REPLIES
from app.constants import (
    ADMIN_MESSAGE_CLIENT_TO_ADMIN,
    ATTACHMENT_DOCUMENT,
    ATTACHMENT_LINK,
    ATTACHMENT_PHOTO,
    MESSAGE_SENDER_USER,
    MESSAGE_TYPE_TEXT,
    MESSAGE_TYPE_VOICE,
    STATE_ADDING_INFORMATION,
    STATE_INTERVIEW,
    STATE_WAITING_DEADLINE,
    STATE_WAITING_INITIAL_DESCRIPTION,
    TERMINAL_STATES,
)
from app.db.repo import Repo
from app.services.application_flow import AI_ERROR_MESSAGE, ApplicationFlowService, InterviewOutcome
from app.services.cancel_button import clear_cancel_button, send_with_single_cancel_button
from app.services.debounce import DebounceAggregator
from app.services.locks import LockRegistry

logger = logging.getLogger(__name__)

router = Router(name="interview")

URL_RE = re.compile(r"https?://\S+")

INPUT_ACCEPTING_STATES = {
    STATE_WAITING_INITIAL_DESCRIPTION,
    STATE_INTERVIEW,
    STATE_WAITING_DEADLINE,
    STATE_ADDING_INFORMATION,
}


async def _send_outcome(
    bot: Bot, repo: Repo, chat_id: int, application: dict, outcome: InterviewOutcome, flow: ApplicationFlowService
) -> None:
    if outcome.kind in ("abandoned", "out_of_scope"):
        await clear_cancel_button(bot, repo, application, chat_id)
        await bot.send_message(chat_id, outcome.message)
    elif outcome.kind == "ask":
        await send_with_single_cancel_button(
            bot, repo, application, chat_id, outcome.message, keyboards.question_keyboard(application["id"])
        )
    elif outcome.kind == "ask_deadline":
        await send_with_single_cancel_button(
            bot, repo, application, chat_id, outcome.message, keyboards.deadline_quick_reply_keyboard(application["id"])
        )
    elif outcome.kind == "understanding":
        await send_with_single_cancel_button(
            bot, repo, application, chat_id, outcome.message,
            keyboards.understanding_keyboard(application["id"], flow.can_add_information(application)),
        )


async def _flush_interview(
    user_id: int,
    payloads: list[tuple[str, int]],
    application_id: int,
    chat_id: int,
    bot: Bot,
    repo: Repo,
    flow: ApplicationFlowService,
    lock_registry: LockRegistry,
) -> None:
    async with lock_registry.get(user_id, application_id):
        application = await repo.applications.get(application_id)
        if application is None or application["state"] in TERMINAL_STATES:
            return

        combined_text = "\n".join(p[0] for p in payloads)
        message_ids = [p[1] for p in payloads]

        try:
            if application["state"] == STATE_WAITING_INITIAL_DESCRIPTION:
                outcome = await flow.process_initial_description(application, combined_text)
            elif application["state"] == STATE_INTERVIEW:
                outcome = await flow.process_interview_message(application, combined_text)
            elif application["state"] == STATE_WAITING_DEADLINE:
                outcome = await flow.process_deadline_answer(application, combined_text)
            elif application["state"] == STATE_ADDING_INFORMATION:
                outcome = await flow.process_add_information_message(application, combined_text)
            else:
                await bot.send_message(chat_id, texts.USE_BUTTONS_REMINDER)
                return
        except AIUnavailableError:
            await bot.send_message(chat_id, AI_ERROR_MESSAGE)
            return

        if outcome.language:
            await repo.messages.set_language_for_ids(message_ids, outcome.language)

        application = await repo.applications.get(application_id)
        await _send_outcome(bot, repo, chat_id, application, outcome, flow)


async def _store_links(repo: Repo, application_id: int, text: str) -> None:
    for url in URL_RE.findall(text):
        await repo.attachments.add(application_id, ATTACHMENT_LINK, None, url, None, None)


async def _handle_no_active_application(message: Message, user: dict, repo: Repo, bot: Bot, admin_id: int) -> None:
    finalized = await repo.applications.list_finalized_for_user(user["id"])
    if not finalized:
        await message.answer(texts.NO_ACTIVE_APPLICATION)
        return

    application = finalized[0]
    text = message.text or message.caption or "(сообщение без текста)"
    await repo.admin_messages.add(application["id"], ADMIN_MESSAGE_CLIENT_TO_ADMIN, text, message.message_id)
    client_label = f"@{user['username']}" if user.get("username") else f"id{user['id']}"
    await bot.send_message(admin_id, f"💬 Сообщение от {client_label} по заявке #{application['id']}:\n\n{text}")
    await message.answer(texts.CLIENT_MESSAGE_FORWARDED)


@router.callback_query(F.data.startswith(f"{CB_DEADLINE_QUICK_PREFIX}:"))
async def cb_deadline_quick_reply(
    callback: CallbackQuery, user: dict | None, repo: Repo, flow: ApplicationFlowService, lock_registry: LockRegistry
) -> None:
    if user is None:
        await callback.answer()
        return

    _, app_id_str, code = callback.data.split(":")
    application_id = int(app_id_str)
    reply = DEADLINE_QUICK_REPLIES.get(code)
    if reply is None:
        await callback.answer()
        return
    text = reply[1]

    async with lock_registry.get(user["id"], application_id):
        application = await repo.applications.get(application_id)
        if application is None or application["user_id"] != user["id"] or application["state"] != STATE_WAITING_DEADLINE:
            await callback.answer()
            return

        await callback.message.edit_reply_markup(reply_markup=None)
        await repo.messages.add(application_id, MESSAGE_SENDER_USER, MESSAGE_TYPE_TEXT, text, None, None)

        # process_deadline_answer never raises AIUnavailableError — a failed LLM
        # parse just falls back to storing the raw quick-reply text (see application_flow.py).
        outcome = await flow.process_deadline_answer(application, text)

        await callback.answer()
        application = await repo.applications.get(application_id)
        await _send_outcome(callback.bot, repo, callback.message.chat.id, application, outcome, flow)


@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(
    message: Message,
    user: dict | None,
    is_admin: bool,
    repo: Repo,
    flow: ApplicationFlowService,
    debounce: DebounceAggregator,
    lock_registry: LockRegistry,
    settings,
    bot: Bot,
    admin_id: int,
) -> None:
    if is_admin or user is None:
        return

    text = message.text
    if len(text) > settings.max_text_length:
        await message.answer(texts.TEXT_TOO_LONG.format(limit=settings.max_text_length))
        return

    application = await repo.applications.get_incomplete_for_user(user["id"])
    if application is None:
        await _handle_no_active_application(message, user, repo, bot, admin_id)
        return

    await _store_links(repo, application["id"], text)

    if application["state"] not in INPUT_ACCEPTING_STATES:
        await message.answer(texts.USE_BUTTONS_REMINDER)
        return

    stored = await repo.messages.add(application["id"], MESSAGE_SENDER_USER, MESSAGE_TYPE_TEXT, text, None, message.message_id)

    async def _flush(uid: int, payloads: list[tuple[str, int]]) -> None:
        await _flush_interview(uid, payloads, application["id"], message.chat.id, bot, repo, flow, lock_registry)

    await debounce.add(user["id"], (text, stored["id"]), _flush)


@router.message(F.voice)
async def handle_voice(
    message: Message,
    user: dict | None,
    is_admin: bool,
    repo: Repo,
    flow: ApplicationFlowService,
    orchestrator: AIOrchestrator,
    debounce: DebounceAggregator,
    lock_registry: LockRegistry,
    settings,
    bot: Bot,
    admin_id: int,
) -> None:
    if is_admin or user is None:
        return

    if message.voice.duration > settings.max_voice_seconds:
        await message.answer(texts.VOICE_TOO_LONG.format(limit=settings.max_voice_seconds))
        return

    application = await repo.applications.get_incomplete_for_user(user["id"])
    if application is None:
        await _handle_no_active_application(message, user, repo, bot, admin_id)
        return

    if application["state"] not in INPUT_ACCEPTING_STATES:
        await message.answer(texts.USE_BUTTONS_REMINDER)
        return

    try:
        buffer = await bot.download(message.voice)
        transcript = await orchestrator.transcribe_voice(buffer.read(), "voice.ogg")
    except AIUnavailableError:
        await message.answer(texts.VOICE_TRANSCRIPTION_FAILED)
        return

    if not transcript.strip():
        await message.answer(texts.VOICE_TRANSCRIPTION_FAILED)
        return

    stored = await repo.messages.add(
        application["id"], MESSAGE_SENDER_USER, MESSAGE_TYPE_VOICE, transcript, None, message.message_id
    )
    await repo.voice_files.add(stored["id"], message.voice.file_id, message.voice.duration, None)

    async def _flush(uid: int, payloads: list[tuple[str, int]]) -> None:
        await _flush_interview(uid, payloads, application["id"], message.chat.id, bot, repo, flow, lock_registry)

    await debounce.add(user["id"], (transcript, stored["id"]), _flush)


@router.message(F.photo | F.document)
async def handle_attachment(
    message: Message, user: dict | None, is_admin: bool, repo: Repo, settings, bot: Bot, admin_id: int
) -> None:
    if is_admin or user is None:
        return

    if message.document:
        file_id = message.document.file_id
        file_size = message.document.file_size or 0
        original_filename = message.document.file_name
        mime_type = message.document.mime_type
        type_ = ATTACHMENT_DOCUMENT
    else:
        photo = message.photo[-1]
        file_id = photo.file_id
        file_size = photo.file_size or 0
        original_filename = None
        mime_type = None
        type_ = ATTACHMENT_PHOTO

    if file_size > settings.max_file_bytes:
        await message.answer(texts.FILE_TOO_LARGE.format(limit=settings.max_file_mb))
        return

    application = await repo.applications.get_incomplete_for_user(user["id"])
    if application is None:
        await _handle_no_active_application(message, user, repo, bot, admin_id)
        return

    await repo.attachments.add(application["id"], type_, file_id, None, original_filename, mime_type)

    if application["state"] == STATE_WAITING_INITIAL_DESCRIPTION:
        await message.answer(texts.FILE_WITHOUT_DESCRIPTION)
    else:
        await message.answer("Файл сохранён и будет доступен администратору.")
