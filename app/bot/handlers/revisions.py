"""Post-completion revisions: trigger, description capture, confirmation
(TZ v1.1 p.67-68, AI Specification v1.1 §33).

Unlike the main interview this is a deliberately single-pass flow (§33.4):
no debounce, no lock, no add-info cycle. If the client sends a new message
while a draft is awaiting confirmation, we simply re-analyze it as a
replacement description — there's no cancel button in this flow (only
"✅ Верно" per p.68.2), so treating a follow-up message as "try again" is
the only forgiving option available."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.ai.orchestrator import AIOrchestrator, AIUnavailableError
from app.bot import keyboards, texts
from app.bot.keyboards import CB_REVISE_CONFIRM_PREFIX, CB_REVISE_PREFIX
from app.constants import STATUS_COMPLETED
from app.db.repo import Repo
from app.services.application_flow import AI_ERROR_MESSAGE
from app.services.revision_drafts import RevisionDraftRegistry
from app.services.revision_flow import RevisionFlowService

router = Router(name="revisions")


async def is_composing_revision(message: Message, user: dict | None, revision_drafts: RevisionDraftRegistry) -> bool:
    return bool(user is not None and revision_drafts.get(user["id"]) is not None)


@router.callback_query(F.data.startswith(f"{CB_REVISE_PREFIX}:"))
async def cb_start_revision(
    callback: CallbackQuery, user: dict | None, repo: Repo, revision_drafts: RevisionDraftRegistry
) -> None:
    if user is None:
        await callback.answer()
        return

    application_id = int(callback.data.split(":")[1])
    application = await repo.applications.get(application_id)
    if application is None or application["user_id"] != user["id"] or application["status"] != STATUS_COMPLETED:
        await callback.answer(texts.REVISION_NOT_AVAILABLE, show_alert=True)
        return

    revision_drafts.start(user["id"], application_id)
    await callback.message.answer(texts.REVISION_DESCRIBE_PROMPT)
    await callback.answer()


async def _analyze_and_prompt(
    message: Message,
    user: dict,
    text: str,
    repo: Repo,
    revision_flow: RevisionFlowService,
    revision_drafts: RevisionDraftRegistry,
    draft,
) -> None:
    application = await repo.applications.get(draft.application_id)
    if application is None or application["status"] != STATUS_COMPLETED:
        revision_drafts.pop(user["id"])
        await message.answer(texts.REVISION_NOT_AVAILABLE)
        return

    try:
        result = await revision_flow.analyze(application, text)
    except AIUnavailableError:
        await message.answer(AI_ERROR_MESSAGE)
        return

    revision_drafts.update(
        user["id"],
        raw_text=text,
        client_message=result.client_message,
        ai_summary=result.ai_summary,
        language=result.language,
        awaiting_confirmation=True,
    )
    await message.answer(
        "Как я понял вашу правку:\n\n" + result.client_message,
        reply_markup=keyboards.revision_confirm_keyboard(draft.application_id),
    )


@router.message(is_composing_revision, F.text & ~F.text.startswith("/"))
async def handle_revision_text(
    message: Message,
    user: dict | None,
    repo: Repo,
    revision_flow: RevisionFlowService,
    revision_drafts: RevisionDraftRegistry,
    settings,
) -> None:
    if user is None:
        return

    text = message.text
    if len(text) > settings.max_text_length:
        await message.answer(texts.TEXT_TOO_LONG.format(limit=settings.max_text_length))
        return

    draft = revision_drafts.get(user["id"])
    await _analyze_and_prompt(message, user, text, repo, revision_flow, revision_drafts, draft)


@router.message(is_composing_revision, F.voice)
async def handle_revision_voice(
    message: Message,
    user: dict | None,
    repo: Repo,
    orchestrator: AIOrchestrator,
    revision_flow: RevisionFlowService,
    revision_drafts: RevisionDraftRegistry,
    settings,
) -> None:
    if user is None:
        return

    if message.voice.duration > settings.max_voice_seconds:
        await message.answer(texts.VOICE_TOO_LONG.format(limit=settings.max_voice_seconds))
        return

    try:
        buffer = await message.bot.download(message.voice)
        transcript = await orchestrator.transcribe_voice(buffer.read(), "voice.ogg")
    except AIUnavailableError:
        await message.answer(texts.VOICE_TRANSCRIPTION_FAILED)
        return

    if not transcript.strip():
        await message.answer(texts.VOICE_TRANSCRIPTION_FAILED)
        return

    draft = revision_drafts.get(user["id"])
    await _analyze_and_prompt(message, user, transcript, repo, revision_flow, revision_drafts, draft)


@router.callback_query(F.data.startswith(f"{CB_REVISE_CONFIRM_PREFIX}:"))
async def cb_confirm_revision(
    callback: CallbackQuery,
    user: dict | None,
    repo: Repo,
    revision_flow: RevisionFlowService,
    revision_drafts: RevisionDraftRegistry,
    bot: Bot,
    admin_id: int,
) -> None:
    if user is None:
        await callback.answer()
        return

    application_id = int(callback.data.split(":")[1])
    draft = revision_drafts.get(user["id"])
    if draft is None or draft.application_id != application_id or not draft.awaiting_confirmation:
        await callback.answer()
        return

    await callback.message.edit_reply_markup(reply_markup=None)
    revision = await revision_flow.confirm(application_id, user["id"], draft.raw_text, draft.client_message, draft.ai_summary)
    revision_drafts.pop(user["id"])

    await callback.message.answer(texts.REVISION_SUBMITTED_TO_CLIENT)
    await callback.answer()

    rank, total_open = await repo.revisions.get_numbering(application_id, revision["id"])
    open_button = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Открыть правку", callback_data=f"adm:rev:{revision['id']}")
    ]])
    await bot.send_message(
        admin_id,
        f"✏️ Новая правка\nЗаявка #{application_id} → Правка #{rank} из {total_open} открытых",
        reply_markup=open_button,
    )
