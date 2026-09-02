"""Creates the /help Telegra.ph page on first startup if TELEGRAPH_HELP_URL isn't
pre-configured (TZ v1.1 p.27). The page is a standalone content artifact, not
part of the AI-interview flow."""

from __future__ import annotations

import json
import logging

import httpx

logger = logging.getLogger(__name__)

TELEGRAPH_API = "https://api.telegra.ph"

HELP_PAGE_TITLE = "Как это работает — сервис разработки ботов и ИИ-автоматизации"

HELP_PAGE_CONTENT: list[dict] = [
    {"tag": "p", "children": [
        "Этот бот помогает быстро оформить заявку на разработку Telegram-бота, "
        "автоматизацию бизнес-процессов или внедрение ИИ в вашу работу — без "
        "необходимости разбираться в технологиях."
    ]},
    {"tag": "h3", "children": ["Кому подойдёт"]},
    {"tag": "p", "children": [
        "Предпринимателям, которым нужен Telegram-бот; компаниям, которым нужна "
        "автоматизация; людям с идеей, но без технических знаний; специалистам, "
        "которым нужна конкретная автоматизация под задачу."
    ]},
    {"tag": "h3", "children": ["Как проходит создание заявки"]},
    {"tag": "ol", "children": [
        {"tag": "li", "children": ["Нажмите /new и кратко (5–7 предложений) опишите, что вам нужно."]},
        {"tag": "li", "children": ["Можно написать текстом или отправить голосовое сообщение."]},
        {"tag": "li", "children": ["ИИ задаст несколько уточняющих вопросов, если это действительно нужно."]},
        {"tag": "li", "children": ["Вы увидите понятное описание того, что будет сделано, и подтвердите его."]},
        {"tag": "li", "children": ["Заявка передаётся в работу, с вами свяжутся в Telegram."]},
    ]},
    {"tag": "h3", "children": ["Форматы ввода"]},
    {"tag": "p", "children": [
        "Текст — до 800 символов за сообщение. Голосовые — до 1 минуты. Файлы, "
        "скриншоты и ссылки принимаются как дополнительные материалы к заявке."
    ]},
    {"tag": "h3", "children": ["Команды"]},
    {"tag": "p", "children": [
        "/new — создать новую заявку. /start — главное меню. /help — эта страница."
    ]},
]


async def ensure_help_page(existing_url: str) -> str:
    """Never allowed to raise: this runs during bot startup, and Telegra.ph being
    unreachable/erroring/returning an unexpected shape must not take the whole bot
    down with it. On any failure, /help falls back to a plain-text message (see
    app.bot.texts.HELP_FALLBACK) instead of a link — degraded, not broken."""
    if existing_url:
        return existing_url

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            account_resp = await client.post(
                f"{TELEGRAPH_API}/createAccount",
                data={"short_name": "SecretaryBot", "author_name": "Секретарь"},
            )
            account_resp.raise_for_status()
            account_data = account_resp.json()
            if not account_data.get("ok"):
                raise RuntimeError(f"Telegra.ph createAccount returned an error: {account_data}")
            access_token = account_data["result"]["access_token"]

            page_resp = await client.post(
                f"{TELEGRAPH_API}/createPage",
                data={
                    "access_token": access_token,
                    "title": HELP_PAGE_TITLE,
                    "author_name": "Секретарь",
                    "content": json.dumps(HELP_PAGE_CONTENT),
                    "return_content": "false",
                },
            )
            page_resp.raise_for_status()
            page_data = page_resp.json()
            if not page_data.get("ok"):
                raise RuntimeError(f"Telegra.ph createPage returned an error: {page_data}")
            url = page_data["result"]["url"]
            logger.info("Created Telegra.ph help page: %s", url)
            return url
    except Exception:
        logger.exception("Failed to create the Telegra.ph help page — /help will use the fallback text instead")
        return ""
