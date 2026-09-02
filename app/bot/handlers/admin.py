"""Admin panel: menu, applications, clients, stats, notes/messages, blocking
(TZ v1.1 p.4, p.43-55, p.60)."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot import keyboards
from app.bot.handlers.admin_mode import mode_screen
from app.bot.texts import ADMIN_MESSAGE_PREFIX, REVISION_DONE_TO_CLIENT
from app.constants import (
    ADMIN_MESSAGE_ADMIN_TO_CLIENT,
    REVISION_STATUS_DONE,
    REVISION_STATUS_EMOJI,
    REVISION_STATUS_IN_PROGRESS,
    REVISION_STATUS_LABELS_RU,
    REVISION_STATUS_NEW,
    REVISION_STATUS_VIEWED,
    STATUS_COMPLETED,
    STATUS_EMOJI,
    STATUS_IN_PROGRESS,
    STATUS_LABELS_RU,
    STATUS_NEW,
    STATUS_REJECTED,
    STATUS_VIEWED,
)
from app.db.repo import Repo
from app.services.admin_mode import AdminModeRegistry

router = Router(name="admin")

# admin_telegram_id -> {"action": "write"|"note", "application_id": int, "client_telegram_id": int}
_pending_admin_actions: dict[int, dict] = {}


def _status_label(status: str) -> str:
    return f"{STATUS_EMOJI.get(status, '')} {STATUS_LABELS_RU.get(status, status)}"


def _client_label(row: dict) -> str:
    if row.get("username"):
        return f"@{row['username']}"
    return row.get("first_name") or f"id{row.get('telegram_id')}"


def _revision_status_label(status: str) -> str:
    return f"{REVISION_STATUS_EMOJI.get(status, '')} {REVISION_STATUS_LABELS_RU.get(status, status)}"


async def send_admin_menu(message: Message, repo: Repo) -> None:
    stats = await repo.applications.stats_overall()
    text = (
        "🛠 Админ-панель\n\n"
        f"🆕 Новые: {stats['new']} · 👀 Просмотрены: {stats['viewed']} · 🔧 В работе: {stats['in_progress']}\n"
        f"✅ Завершены: {stats['completed']} · ❌ Отклонены: {stats['rejected']}\n"
        f"👥 Клиентов: {stats['clients']} · 🚫 Заблокировано: {stats['blocked']}"
    )
    await message.answer(text, reply_markup=keyboards.admin_main_menu_keyboard())


@router.message(Command("admin"))
async def cmd_admin(message: Message, is_admin: bool, repo: Repo) -> None:
    if not is_admin:
        return
    await send_admin_menu(message, repo)


async def is_admin_text_filter(message: Message, is_admin: bool) -> bool:
    return bool(is_admin and message.text and not message.text.startswith("/"))


@router.message(is_admin_text_filter)
async def handle_admin_pending_text(message: Message, repo: Repo, bot: Bot) -> None:
    pending = _pending_admin_actions.pop(message.from_user.id, None)
    if pending is None:
        return

    if pending["action"] == "write":
        await repo.admin_messages.add(
            pending.get("application_id"), ADMIN_MESSAGE_ADMIN_TO_CLIENT, message.text, message.message_id
        )
        await bot.send_message(pending["client_telegram_id"], ADMIN_MESSAGE_PREFIX + message.text)
        await message.answer("Сообщение отправлено клиенту.")
    elif pending["action"] == "note":
        await repo.admin_notes.add(pending["application_id"], message.from_user.id, message.text)
        await message.answer("Заметка добавлена.")


# --- Applications list ---

async def _render_application_list(callback: CallbackQuery, repo: Repo, status: str | None) -> None:
    apps = await repo.applications.list_by_status(status, limit=20)
    title = f"Заявки: {_status_label(status)}" if status else "Все заявки"
    if not apps:
        await callback.message.edit_text(title + "\n\nПусто.", reply_markup=keyboards.back_to_menu_keyboard())
        return

    kb_rows = [
        [InlineKeyboardButton(
            text=f"#{a['id']} {_status_label(a['status'])} — {_client_label(a)}",
            callback_data=f"adm:app:{a['id']}",
        )]
        for a in apps
    ]
    kb_rows.append([InlineKeyboardButton(text="« Меню", callback_data=keyboards.CB_ADMIN_MENU)])
    await callback.message.edit_text(title + f"\n\nВсего: {len(apps)}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))


@router.callback_query(F.data == keyboards.CB_ADMIN_MENU)
async def cb_admin_menu(callback: CallbackQuery, is_admin: bool, repo: Repo) -> None:
    if not is_admin:
        await callback.answer()
        return
    stats = await repo.applications.stats_overall()
    text = (
        "🛠 Админ-панель\n\n"
        f"🆕 Новые: {stats['new']} · 👀 Просмотрены: {stats['viewed']} · 🔧 В работе: {stats['in_progress']}\n"
        f"✅ Завершены: {stats['completed']} · ❌ Отклонены: {stats['rejected']}\n"
        f"👥 Клиентов: {stats['clients']} · 🚫 Заблокировано: {stats['blocked']}"
    )
    await callback.message.edit_text(text, reply_markup=keyboards.admin_main_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == keyboards.CB_ADMIN_NEW)
async def cb_admin_new(callback: CallbackQuery, is_admin: bool, repo: Repo) -> None:
    if not is_admin:
        await callback.answer()
        return
    await _render_application_list(callback, repo, STATUS_NEW)
    await callback.answer()


@router.callback_query(F.data == keyboards.CB_ADMIN_ALL)
async def cb_admin_all(callback: CallbackQuery, is_admin: bool, repo: Repo) -> None:
    if not is_admin:
        await callback.answer()
        return
    await callback.message.edit_text("Выберите фильтр или откройте всё:", reply_markup=keyboards.admin_status_filter_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith(f"{keyboards.CB_ADMIN_FILTER_PREFIX}:"))
async def cb_admin_filter(callback: CallbackQuery, is_admin: bool, repo: Repo) -> None:
    if not is_admin:
        await callback.answer()
        return
    status = callback.data.split(":")[2]
    await _render_application_list(callback, repo, status)
    await callback.answer()


@router.callback_query(F.data == keyboards.CB_ADMIN_STATS)
async def cb_admin_stats(callback: CallbackQuery, is_admin: bool, repo: Repo) -> None:
    if not is_admin:
        await callback.answer()
        return
    overall = await repo.applications.stats_overall()
    d7 = await repo.applications.stats_period(7)
    d30 = await repo.applications.stats_period(30)
    text = (
        "📊 Статистика\n\n"
        "За всё время:\n"
        f"Клиентов: {overall['clients']} · Заявок: {overall['applications']}\n"
        f"🆕 {overall['new']} · 👀 {overall['viewed']} · 🔧 {overall['in_progress']} · "
        f"✅ {overall['completed']} · ❌ {overall['rejected']} · 🚫 {overall['blocked']}\n\n"
        "За 7 дней:\n"
        f"Новых клиентов: {d7['new_clients']} · Новых заявок: {d7['new_applications']} · Завершено: {d7['completed']}\n\n"
        "За 30 дней:\n"
        f"Новых клиентов: {d30['new_clients']} · Новых заявок: {d30['new_applications']} · Завершено: {d30['completed']}"
    )
    await callback.message.edit_text(text, reply_markup=keyboards.back_to_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == keyboards.CB_ADMIN_BLOCKED)
async def cb_admin_blocked(callback: CallbackQuery, is_admin: bool, repo: Repo) -> None:
    if not is_admin:
        await callback.answer()
        return
    blocked = await repo.users.list_blocked()
    if not blocked:
        await callback.message.edit_text("🚫 Заблокированные\n\nПусто.", reply_markup=keyboards.back_to_menu_keyboard())
        await callback.answer()
        return

    rows = [[InlineKeyboardButton(text=_client_label(u), callback_data=f"adm:client:{u['id']}")] for u in blocked]
    rows.append([InlineKeyboardButton(text="« Меню", callback_data=keyboards.CB_ADMIN_MENU)])
    await callback.message.edit_text("🚫 Заблокированные клиенты:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


@router.callback_query(F.data == keyboards.CB_ADMIN_MODE)
async def cb_admin_mode(callback: CallbackQuery, is_admin: bool, admin_mode: AdminModeRegistry) -> None:
    if not is_admin:
        await callback.answer()
        return
    text, keyboard = mode_screen(admin_mode.get(callback.from_user.id))
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == keyboards.CB_ADMIN_CLIENTS)
async def cb_admin_clients(callback: CallbackQuery, is_admin: bool, repo: Repo) -> None:
    if not is_admin:
        await callback.answer()
        return
    clients = await repo.users.list_clients(limit=30)

    rows = [
        [InlineKeyboardButton(
            text=f"{_client_label(c)} ({c['applications_count']} заявок)",
            callback_data=f"adm:client:{c['id']}",
        )]
        for c in clients
    ]
    rows.append([InlineKeyboardButton(text="« Меню", callback_data=keyboards.CB_ADMIN_MENU)])
    await callback.message.edit_text("👥 Клиенты:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


# --- Application card ---

async def _open_application_card(target, application_id: int, repo: Repo, bot: Bot) -> None:
    application = await repo.applications.get_with_client(application_id)
    if application is None:
        await target.answer("Заявка не найдена.")
        return

    if application["status"] == STATUS_NEW:
        await repo.applications.update_status(application_id, STATUS_VIEWED)
        application["status"] = STATUS_VIEWED

    notes = await repo.admin_notes.list_for_application(application_id)
    lines = [
        f"Заявка #{application['id']} — {_status_label(application['status'])}",
        f"Клиент: {_client_label(application)} (id{application['telegram_id']})",
        f"Язык: {application.get('language_code') or '—'}",
        f"Создана: {application['created_at']:%d.%m.%Y %H:%M}",
        f"Срок запуска: {application.get('deadline_text') or '—'}",
        "",
        "Задача глазами клиента:",
        application.get("client_understanding_text") or "(понимание ещё не сформировано)",
    ]
    if notes:
        lines.append("")
        lines.append("Заметки администратора:")
        for n in notes:
            lines.append(f"• {n['created_at']:%d.%m %H:%M} — {n['text']}")

    is_blocked = bool((await repo.users.get_client_card(application["user_id"]) or {}).get("is_blocked"))
    await target.answer(
        "\n".join(lines), reply_markup=keyboards.admin_application_card_keyboard(application_id, is_blocked)
    )

    chat_id = target.chat.id

    if application.get("tz_markdown_content"):
        file = BufferedInputFile(
            application["tz_markdown_content"].encode("utf-8"),
            filename=application.get("tz_markdown_path") or f"TZ_{application_id}.md",
        )
        await bot.send_document(chat_id, file)

    voices = await repo.voice_files.list_for_application(application_id)
    for v in voices:
        try:
            await bot.send_voice(chat_id, v["telegram_file_id"])
        except Exception:
            pass

    attachments = await repo.attachments.list_for_application(application_id)
    if attachments:
        att_lines = ["Материалы заявки:"]
        for a in attachments:
            if a["type"] == "link":
                att_lines.append(f"🔗 {a['url']}")
            elif a["type"] == "document" and a.get("telegram_file_id"):
                await bot.send_document(chat_id, a["telegram_file_id"], caption=a.get("original_filename") or "")
            elif a["type"] == "photo" and a.get("telegram_file_id"):
                await bot.send_photo(chat_id, a["telegram_file_id"])
        if len(att_lines) > 1:
            await bot.send_message(chat_id, "\n".join(att_lines))

    if application["status"] == STATUS_COMPLETED:
        revisions = await repo.revisions.list_for_application(application_id)
        if revisions:
            rows = [
                [InlineKeyboardButton(
                    text=f"✏️ Правка #{r['id']} — {_revision_status_label(r['status'])}",
                    callback_data=f"adm:rev:{r['id']}",
                )]
                for r in revisions
            ]
            await bot.send_message(
                chat_id, "Правки по заявке:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
            )


@router.callback_query(F.data.regexp(r"^adm:app:\d+$"))
async def cb_open_application(callback: CallbackQuery, is_admin: bool, repo: Repo, bot: Bot) -> None:
    if not is_admin:
        await callback.answer()
        return
    application_id = int(callback.data.split(":")[2])
    await _open_application_card(callback.message, application_id, repo, bot)
    await callback.answer()


@router.callback_query(F.data.regexp(r"^adm:app:\d+:(viewed|progress|done|reject)$"))
async def cb_application_status_action(callback: CallbackQuery, is_admin: bool, repo: Repo, bot: Bot) -> None:
    if not is_admin:
        await callback.answer()
        return
    _, _, app_id_str, action = callback.data.split(":")
    application_id = int(app_id_str)

    status_map = {
        "viewed": STATUS_VIEWED, "progress": STATUS_IN_PROGRESS, "done": STATUS_COMPLETED, "reject": STATUS_REJECTED,
    }
    await repo.applications.update_status(application_id, status_map[action])
    await repo.events.log("status_change", application_id=application_id, payload={"new_status": status_map[action]})
    await _open_application_card(callback.message, application_id, repo, bot)
    await callback.answer("Статус обновлён")


@router.callback_query(F.data.regexp(r"^adm:app:\d+:client$"))
async def cb_application_open_client(callback: CallbackQuery, is_admin: bool, repo: Repo, bot: Bot) -> None:
    if not is_admin:
        await callback.answer()
        return
    application_id = int(callback.data.split(":")[2])
    application = await repo.applications.get(application_id)
    if application is None:
        await callback.answer()
        return
    await _open_client_card(callback.message, application["user_id"], repo)
    await callback.answer()


@router.callback_query(F.data.regexp(r"^adm:app:\d+:write$"))
async def cb_application_write(callback: CallbackQuery, is_admin: bool, repo: Repo) -> None:
    if not is_admin:
        await callback.answer()
        return
    application_id = int(callback.data.split(":")[2])
    application = await repo.applications.get_with_client(application_id)
    if application is None:
        await callback.answer()
        return
    _pending_admin_actions[callback.from_user.id] = {
        "action": "write", "application_id": application_id, "client_telegram_id": application["telegram_id"],
    }
    await callback.message.answer("Введите текст сообщения клиенту:")
    await callback.answer()


@router.callback_query(F.data.regexp(r"^adm:app:\d+:note$"))
async def cb_application_note(callback: CallbackQuery, is_admin: bool) -> None:
    if not is_admin:
        await callback.answer()
        return
    application_id = int(callback.data.split(":")[2])
    _pending_admin_actions[callback.from_user.id] = {"action": "note", "application_id": application_id}
    await callback.message.answer("Введите текст заметки (видна только администратору):")
    await callback.answer()


@router.callback_query(F.data.regexp(r"^adm:app:\d+:block$"))
async def cb_application_block_prompt(callback: CallbackQuery, is_admin: bool, repo: Repo) -> None:
    if not is_admin:
        await callback.answer()
        return
    application_id = int(callback.data.split(":")[2])
    application = await repo.applications.get_with_client(application_id)
    if application is None:
        await callback.answer()
        return
    label = _client_label(application)
    await callback.message.answer(
        f"Заблокировать пользователя {label}?",
        reply_markup=keyboards.admin_confirm_block_keyboard(application["user_id"], label),
    )
    await callback.answer()


@router.callback_query(F.data.regexp(r"^adm:app:\d+:unblock$"))
async def cb_application_unblock(callback: CallbackQuery, is_admin: bool, repo: Repo, bot: Bot) -> None:
    if not is_admin:
        await callback.answer()
        return
    application_id = int(callback.data.split(":")[2])
    application = await repo.applications.get(application_id)
    if application is None:
        await callback.answer()
        return
    await repo.users.set_blocked(application["user_id"], False)
    await _open_application_card(callback.message, application_id, repo, bot)
    await callback.answer("Разблокирован")


# --- Client card ---

async def _open_client_card(target, user_id: int, repo: Repo) -> None:
    client = await repo.users.get_client_card(user_id)
    if client is None:
        await target.answer("Клиент не найден.")
        return
    apps = await repo.applications.list_for_user(user_id)

    lines = [
        f"👤 {_client_label(client)}",
        f"Telegram ID: {client['telegram_id']}",
        f"Язык: {client.get('language_code') or '—'}",
        f"Первое обращение: {client['created_at']:%d.%m.%Y}",
        f"Последняя активность: {client['last_active_at']:%d.%m.%Y %H:%M}",
        f"Заявок: {len(apps)}",
        f"Заблокирован: {'да' if client['is_blocked'] else 'нет'}",
    ]
    if apps:
        lines.append("")
        lines.append("Заявки:")
        for a in apps:
            lines.append(f"#{a['id']} {_status_label(a['status'])} — {a['created_at']:%d.%m.%Y}")

    await target.answer("\n".join(lines), reply_markup=keyboards.admin_client_card_keyboard(user_id, client["is_blocked"]))


@router.callback_query(F.data.regexp(r"^adm:client:\d+$"))
async def cb_open_client(callback: CallbackQuery, is_admin: bool, repo: Repo) -> None:
    if not is_admin:
        await callback.answer()
        return
    user_id = int(callback.data.split(":")[2])
    await _open_client_card(callback.message, user_id, repo)
    await callback.answer()


@router.callback_query(F.data.regexp(r"^adm:client:\d+:write$"))
async def cb_client_write(callback: CallbackQuery, is_admin: bool, repo: Repo) -> None:
    if not is_admin:
        await callback.answer()
        return
    user_id = int(callback.data.split(":")[2])
    client = await repo.users.get_client_card(user_id)
    if client is None:
        await callback.answer()
        return
    apps = await repo.applications.list_for_user(user_id)
    _pending_admin_actions[callback.from_user.id] = {
        "action": "write",
        "application_id": apps[0]["id"] if apps else None,
        "client_telegram_id": client["telegram_id"],
    }
    await callback.message.answer("Введите текст сообщения клиенту:")
    await callback.answer()


@router.callback_query(F.data.regexp(r"^adm:client:\d+:block$"))
async def cb_client_block_prompt(callback: CallbackQuery, is_admin: bool, repo: Repo) -> None:
    if not is_admin:
        await callback.answer()
        return
    user_id = int(callback.data.split(":")[2])
    client = await repo.users.get_client_card(user_id)
    if client is None:
        await callback.answer()
        return
    label = _client_label(client)
    await callback.message.answer(
        f"Заблокировать пользователя {label}?", reply_markup=keyboards.admin_confirm_block_keyboard(user_id, label)
    )
    await callback.answer()


@router.callback_query(F.data.regexp(r"^adm:client:\d+:block_confirm$"))
async def cb_client_block_confirm(callback: CallbackQuery, is_admin: bool, repo: Repo) -> None:
    if not is_admin:
        await callback.answer()
        return
    user_id = int(callback.data.split(":")[2])
    await repo.users.set_blocked(user_id, True)
    await _open_client_card(callback.message, user_id, repo)
    await callback.answer("Заблокирован")


@router.callback_query(F.data.regexp(r"^adm:client:\d+:unblock$"))
async def cb_client_unblock(callback: CallbackQuery, is_admin: bool, repo: Repo) -> None:
    if not is_admin:
        await callback.answer()
        return
    user_id = int(callback.data.split(":")[2])
    await repo.users.set_blocked(user_id, False)
    await _open_client_card(callback.message, user_id, repo)
    await callback.answer("Разблокирован")


# --- Revisions (v1.2) ---

async def _open_revision_card(target, revision_id: int, repo: Repo) -> None:
    revision = await repo.revisions.get(revision_id)
    if revision is None:
        await target.answer("Правка не найдена.")
        return

    if revision["status"] == REVISION_STATUS_NEW:
        await repo.revisions.update_status(revision_id, REVISION_STATUS_VIEWED)
        revision["status"] = REVISION_STATUS_VIEWED

    rank, total_open = await repo.revisions.get_numbering(revision["application_id"], revision_id)
    lines = [
        f"Заявка #{revision['application_id']} → Правка #{rank} из {total_open} открытых",
        f"Статус: {_revision_status_label(revision['status'])}",
        f"Создана: {revision['created_at']:%d.%m.%Y %H:%M}",
        "",
        "Как понял клиент (подтверждено):",
        revision.get("client_understanding_text") or "—",
        "",
        "Для администратора:",
        revision.get("ai_summary") or "—",
    ]
    await target.answer(
        "\n".join(lines),
        reply_markup=keyboards.admin_revision_card_keyboard(revision_id, revision["application_id"]),
    )


@router.callback_query(F.data.regexp(r"^adm:rev:\d+$"))
async def cb_open_revision(callback: CallbackQuery, is_admin: bool, repo: Repo) -> None:
    if not is_admin:
        await callback.answer()
        return
    revision_id = int(callback.data.split(":")[2])
    await _open_revision_card(callback.message, revision_id, repo)
    await callback.answer()


@router.callback_query(F.data.regexp(r"^adm:rev:\d+:(viewed|progress|done)$"))
async def cb_revision_status_action(callback: CallbackQuery, is_admin: bool, repo: Repo, bot: Bot) -> None:
    if not is_admin:
        await callback.answer()
        return
    _, _, rev_id_str, action = callback.data.split(":")
    revision_id = int(rev_id_str)

    status_map = {"viewed": REVISION_STATUS_VIEWED, "progress": REVISION_STATUS_IN_PROGRESS, "done": REVISION_STATUS_DONE}
    new_status = status_map[action]
    await repo.revisions.update_status(revision_id, new_status)

    if new_status == REVISION_STATUS_DONE:
        revision = await repo.revisions.get(revision_id)
        client = await repo.users.get_client_card(revision["user_id"])
        if client:
            try:
                await bot.send_message(
                    client["telegram_id"], REVISION_DONE_TO_CLIENT.format(application_id=revision["application_id"])
                )
            except Exception:
                pass

    await _open_revision_card(callback.message, revision_id, repo)
    await callback.answer("Статус обновлён")
