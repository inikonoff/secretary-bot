"""User upsert/blocking + rate limiting, both applied before any handler or LLM call
(TZ v1.1 p.20.2, p.48)."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from app.constants import EVENT_RATE_LIMIT_HIT
from app.db.repo import Repo
from app.services.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class UserContextMiddleware(BaseMiddleware):
    """Upserts the Telegram user, drops updates from blocked users, injects `user` into data."""

    def __init__(self, repo: Repo, admin_id: int):
        self._repo = repo
        self._admin_id = admin_id

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user is None:
            return await handler(event, data)

        if tg_user.id == self._admin_id:
            data["is_admin"] = True
            data["user"] = None
            return await handler(event, data)

        data["is_admin"] = False
        user = await self._repo.users.get_or_create(tg_user.id, tg_user.username, tg_user.first_name)
        if user["is_blocked"]:
            return  # silently drop; TZ doesn't specify client-facing copy for blocked users
        data["user"] = user
        return await handler(event, data)


class RateLimitMiddleware(BaseMiddleware):
    """Technical throttle independent from the interview clarifying-questions limit (p.20.1 vs p.20.2)."""

    def __init__(self, repo: Repo, limiter: RateLimiter):
        self._repo = repo
        self._limiter = limiter

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("user")
        if user is None:
            return await handler(event, data)

        if not self._limiter.allow(user["id"]):
            await self._repo.events.log(EVENT_RATE_LIMIT_HIT, user_id=user["id"])
            logger.info("rate limit hit for user_id=%s", user["id"])
            return
        return await handler(event, data)
