"""Webhook entrypoint: aiohttp Web Service on Render free tier (TZ v1.1 p.40, deploy note)."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from app.ai.orchestrator import AIOrchestrator
from app.bot.middlewares import RateLimitMiddleware, UserContextMiddleware
from app.bot.router import root_router
from app.config import get_settings
from app.db.pool import create_pool
from app.db.repo import Repo
from app.db.schema_apply import apply_schema
from app.logging_config import configure_logging
from app.services.admin_mode import AdminModeRegistry
from app.services.application_flow import ApplicationFlowService
from app.services.debounce import DebounceAggregator
from app.services.locks import LockRegistry
from app.services.rate_limiter import RateLimiter
from app.services.reminders import reminder_loop
from app.services.revision_drafts import RevisionDraftRegistry
from app.services.revision_flow import RevisionFlowService
from app.services.supabase_keepalive import supabase_keepalive_loop
from app.services.telegraph import ensure_help_page
from app.services.tz_generator import TZGeneratorService

logger = logging.getLogger(__name__)


async def on_startup(bot: Bot, dp: Dispatcher) -> None:
    settings = dp["settings"]
    await apply_schema(dp["pool"])

    help_url = await ensure_help_page(settings.telegraph_help_url)
    dp["telegraph_help_url"] = help_url

    await bot.set_webhook(
        settings.webhook_url,
        secret_token=settings.webhook_secret,
        drop_pending_updates=False,
    )

    dp["reminder_task"] = asyncio.create_task(
        reminder_loop(bot, dp["repo"], settings.incomplete_session_reminder_hours)
    )
    dp["supabase_keepalive_task"] = asyncio.create_task(
        supabase_keepalive_loop(dp["pool"], settings.supabase_keepalive_interval_seconds)
    )
    logger.info("Bot started, webhook set to %s", settings.webhook_url)


async def on_shutdown(bot: Bot, dp: Dispatcher) -> None:
    for task_key in ("reminder_task", "supabase_keepalive_task"):
        task = dp.get(task_key)
        if task:
            task.cancel()
    await dp["pool"].close()
    await bot.session.close()


async def health(request: web.Request) -> web.Response:
    return web.Response(text="ok")


def build_app() -> web.Application:
    settings = get_settings()
    configure_logging(settings.log_level)

    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(root_router)

    async def _init(app: web.Application) -> None:
        pool = await create_pool(settings.database_url)
        repo = Repo(pool)
        orchestrator = AIOrchestrator(
            groq_api_key=settings.groq_api_key,
            openrouter_api_key=settings.openrouter_api_key,
            groq_model_interview=settings.groq_model_interview,
            groq_model_final=settings.groq_model_final,
            groq_whisper_model=settings.groq_whisper_model,
            openrouter_model_interview=settings.openrouter_model_interview,
            openrouter_model_final=settings.openrouter_model_final,
        )
        flow = ApplicationFlowService(repo, orchestrator, settings)
        tz_generator = TZGeneratorService(repo, orchestrator)
        revision_flow = RevisionFlowService(repo, orchestrator)

        dp["settings"] = settings
        dp["pool"] = pool
        dp["repo"] = repo
        dp["orchestrator"] = orchestrator
        dp["flow"] = flow
        dp["tz_generator"] = tz_generator
        dp["revision_flow"] = revision_flow
        dp["revision_drafts"] = RevisionDraftRegistry()
        dp["debounce"] = DebounceAggregator(settings.debounce_seconds)
        dp["lock_registry"] = LockRegistry()
        dp["admin_id"] = settings.admin_id
        dp["telegraph_help_url"] = settings.telegraph_help_url
        admin_mode = AdminModeRegistry()
        dp["admin_mode"] = admin_mode

        dp.update.outer_middleware(UserContextMiddleware(repo, settings.admin_id, admin_mode))
        dp.message.outer_middleware(RateLimitMiddleware(repo, RateLimiter(settings.rate_limit_messages, settings.rate_limit_window_seconds)))

        await on_startup(bot, dp)

    async def _cleanup(app: web.Application) -> None:
        await on_shutdown(bot, dp)

    app = web.Application()
    app.on_startup.append(_init)
    app.on_cleanup.append(_cleanup)
    app.router.add_get("/health", health)

    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=settings.webhook_secret).register(
        app, path=settings.webhook_path
    )
    setup_application(app, dp, bot=bot)

    return app


def main() -> None:
    settings = get_settings()
    web.run_app(build_app(), host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()
