"""/mode — lets the admin toggle their own account between the real Admin
experience and a full simulation of the client flow (see
app/services/admin_mode.py for the "why" and the routing implications).

This command deliberately checks the RAW Telegram ID, not the `is_admin` flag
that the rest of the bot uses — that flag reflects the currently simulated
role, so gating this on it would strand the admin in User mode with no way
back once they've switched."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.keyboards import CB_ADMIN_MENU
from app.services.admin_mode import ADMIN_MODE, USER_MODE, AdminModeRegistry

router = Router(name="admin_mode")

MODE_LABELS = {
    ADMIN_MODE: "🛠 Admin",
    USER_MODE: "👤 User (тест как клиент)",
}

MODE_EXPLANATION = (
    "Admin — обычная админ-панель.\n"
    "User — бот общается с вами как с потенциальным заказчиком: можно от "
    "своего лица пройти весь путь оформления заявки для теста (включая "
    "реальные уведомления администратору — они тоже придут вам)."
)


def mode_screen(current_mode: str) -> tuple[str, InlineKeyboardMarkup]:
    target = USER_MODE if current_mode == ADMIN_MODE else ADMIN_MODE
    target_label = "👤 Переключиться на User" if current_mode == ADMIN_MODE else "🛠 Вернуться в Admin"
    text = f"Текущий режим: {MODE_LABELS[current_mode]}\n\n{MODE_EXPLANATION}"

    rows = [[InlineKeyboardButton(text=target_label, callback_data=f"mode_toggle:{target}")]]
    if current_mode == ADMIN_MODE:
        rows.append([InlineKeyboardButton(text="« Меню", callback_data=CB_ADMIN_MENU)])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


async def _is_real_admin(message: Message, admin_id: int) -> bool:
    return message.from_user.id == admin_id


@router.message(Command("mode"), _is_real_admin)
async def cmd_mode(message: Message, admin_mode: AdminModeRegistry) -> None:
    text, keyboard = mode_screen(admin_mode.get(message.from_user.id))
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("mode_toggle:"))
async def cb_mode_toggle(callback: CallbackQuery, admin_mode: AdminModeRegistry, admin_id: int) -> None:
    if callback.from_user.id != admin_id:
        await callback.answer()
        return

    target = callback.data.split(":")[1]
    admin_mode.set(callback.from_user.id, target)
    await callback.message.edit_reply_markup(reply_markup=None)

    if target == USER_MODE:
        await callback.message.answer(
            "Режим переключён на User. Отправьте /start, чтобы пройти путь клиента. "
            "Вернуться в Admin в любой момент — командой /mode."
        )
    else:
        text, keyboard = mode_screen(ADMIN_MODE)
        await callback.message.answer(text, reply_markup=keyboard)
    await callback.answer()
