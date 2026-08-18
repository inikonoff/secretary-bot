from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

CB_CREATE_APPLICATION = "create_app"
CB_CANCEL_PREFIX = "cancel_app"
CB_CONFIRM_OK_PREFIX = "confirm_ok"
CB_ADD_INFO_PREFIX = "add_info"

CB_ADMIN_MENU = "adm:menu"
CB_ADMIN_NEW = "adm:new"
CB_ADMIN_ALL = "adm:all"
CB_ADMIN_CLIENTS = "adm:clients"
CB_ADMIN_STATS = "adm:stats"
CB_ADMIN_BLOCKED = "adm:blocked"
CB_ADMIN_FILTER_PREFIX = "adm:filter"
CB_ADMIN_APP_PREFIX = "adm:app"
CB_ADMIN_CLIENT_PREFIX = "adm:client"


def create_application_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать заявку", callback_data=CB_CREATE_APPLICATION)],
    ])


def incomplete_session_keyboard(application_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить заявку", callback_data=f"{CB_CANCEL_PREFIX}:{application_id}")],
    ])


def question_keyboard(application_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить", callback_data=f"{CB_CANCEL_PREFIX}:{application_id}")],
    ])


def understanding_keyboard(application_id: int, can_add_info: bool) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="✅ Верно", callback_data=f"{CB_CONFIRM_OK_PREFIX}:{application_id}")]]
    if can_add_info:
        rows.append([InlineKeyboardButton(text="➕ Добавить информацию", callback_data=f"{CB_ADD_INFO_PREFIX}:{application_id}")])
    rows.append([InlineKeyboardButton(text="❌ Отменить", callback_data=f"{CB_CANCEL_PREFIX}:{application_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def new_application_only_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать новую", callback_data=CB_CREATE_APPLICATION)],
    ])


# --- Admin ---

def admin_main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🆕 Новые заявки", callback_data=CB_ADMIN_NEW)],
        [InlineKeyboardButton(text="📋 Все заявки", callback_data=CB_ADMIN_ALL)],
        [InlineKeyboardButton(text="👥 Клиенты", callback_data=CB_ADMIN_CLIENTS)],
        [InlineKeyboardButton(text="📊 Статистика", callback_data=CB_ADMIN_STATS)],
        [InlineKeyboardButton(text="🚫 Заблокированные", callback_data=CB_ADMIN_BLOCKED)],
    ])


def admin_status_filter_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🆕 Новые", callback_data=f"{CB_ADMIN_FILTER_PREFIX}:new")],
        [InlineKeyboardButton(text="👀 Просмотрены", callback_data=f"{CB_ADMIN_FILTER_PREFIX}:viewed")],
        [InlineKeyboardButton(text="🔧 В работе", callback_data=f"{CB_ADMIN_FILTER_PREFIX}:in_progress")],
        [InlineKeyboardButton(text="✅ Завершены", callback_data=f"{CB_ADMIN_FILTER_PREFIX}:completed")],
        [InlineKeyboardButton(text="❌ Отклонены", callback_data=f"{CB_ADMIN_FILTER_PREFIX}:rejected")],
        [InlineKeyboardButton(text="« Меню", callback_data=CB_ADMIN_MENU)],
    ])


def admin_application_card_keyboard(application_id: int, is_blocked: bool) -> InlineKeyboardMarkup:
    block_button = (
        InlineKeyboardButton(text="🔓 Разблокировать", callback_data=f"{CB_ADMIN_APP_PREFIX}:{application_id}:unblock")
        if is_blocked else
        InlineKeyboardButton(text="🚫 Заблокировать", callback_data=f"{CB_ADMIN_APP_PREFIX}:{application_id}:block")
    )
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👀 Просмотрена", callback_data=f"{CB_ADMIN_APP_PREFIX}:{application_id}:viewed"),
            InlineKeyboardButton(text="🔧 В работу", callback_data=f"{CB_ADMIN_APP_PREFIX}:{application_id}:progress"),
        ],
        [
            InlineKeyboardButton(text="✅ Завершить", callback_data=f"{CB_ADMIN_APP_PREFIX}:{application_id}:done"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"{CB_ADMIN_APP_PREFIX}:{application_id}:reject"),
        ],
        [
            InlineKeyboardButton(text="👤 Клиент", callback_data=f"{CB_ADMIN_APP_PREFIX}:{application_id}:client"),
            InlineKeyboardButton(text="💬 Написать", callback_data=f"{CB_ADMIN_APP_PREFIX}:{application_id}:write"),
        ],
        [
            InlineKeyboardButton(text="📝 Добавить заметку", callback_data=f"{CB_ADMIN_APP_PREFIX}:{application_id}:note"),
            block_button,
        ],
        [InlineKeyboardButton(text="« Меню", callback_data=CB_ADMIN_MENU)],
    ])


def admin_client_card_keyboard(user_id: int, is_blocked: bool) -> InlineKeyboardMarkup:
    block_button = (
        InlineKeyboardButton(text="🔓 Разблокировать", callback_data=f"{CB_ADMIN_CLIENT_PREFIX}:{user_id}:unblock")
        if is_blocked else
        InlineKeyboardButton(text="🚫 Заблокировать", callback_data=f"{CB_ADMIN_CLIENT_PREFIX}:{user_id}:block")
    )
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Написать", callback_data=f"{CB_ADMIN_CLIENT_PREFIX}:{user_id}:write")],
        [block_button],
        [InlineKeyboardButton(text="« Меню", callback_data=CB_ADMIN_MENU)],
    ])


def admin_confirm_block_keyboard(user_id: int, username: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, заблокировать", callback_data=f"{CB_ADMIN_CLIENT_PREFIX}:{user_id}:block_confirm"),
            InlineKeyboardButton(text="Отмена", callback_data=f"{CB_ADMIN_CLIENT_PREFIX}:{user_id}"),
        ],
    ])


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="« Меню", callback_data=CB_ADMIN_MENU)],
    ])
