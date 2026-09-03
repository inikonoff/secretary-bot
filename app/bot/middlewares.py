"""User upsert/blocking + rate limiting, both applied before any handler or LLM call
(TZ v1.1 p.20.2, p.48)."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from app.constants import EVENT_RATE_LIMIT_HIT
from app.db.repo import Repo
from app.services.admin_mode import USER_MODE, AdminModeRegistry
from app.services.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class UserContextMiddleware(BaseMiddleware):
    """Upserts the Telegram user, drops updates from blocked users, injects `user` into data.

    `is_admin` reflects the CURRENTLY SIMULATED role, not raw Telegram identity: while
    the admin has switched themselves into User mode (see app/services/admin_mode.py),
    this deliberately reports is_admin=False and populates `user` with their own upserted
    row, so every existing is_admin-gated handler routes them through the real client
    experience with zero changes. The `/mode` command itself bypasses this and checks the
    raw Telegram ID instead, so switching back is never blocked by the simulated state.
    """

    def __init__(self, repo: Repo, admin_id: int, admin_mode: AdminModeRegistry):
        self._repo = repo
        self._admin_id = admin_id
        self._admin_mode = admin_mode

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user is None:
            return await handler(event, data)

        is_real_admin = tg_user.id == self._admin_id
        simulating_user = is_real_admin and self._admin_mode.get(tg_user.id) == USER_MODE

        if is_real_admin and not simulating_user:
            data["is_admin"] = True
            data["user"] = None
            return await handler(event, data)

        data["is_admin"] = False
        user = await self._repo.users.get_or_create(tg_user.id, tg_user.username, tg_user.first_name)
        # The real admin is never actually locked out by is_blocked, even while
        # simulating User mode: this middleware runs before any command routing
        # (including /mode), so a silent drop here would strand them with no way
        # back short of a redeploy. Blocking still "sticks" for every other user.
        if user["is_blocked"] and not is_real_admin:
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
