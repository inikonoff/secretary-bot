"""Background keep-alive ping so the Supabase free-tier project doesn't get
auto-paused after ~7 days without database activity. Render's own sleep problem
is solved separately by UptimeRobot polling /health (see app/main.py) — this
loop exists purely for Supabase's independent inactivity timer, same rationale
as the equivalent loop in the PixKeep bot."""

from __future__ import annotations

import asyncio
import logging

import asyncpg

logger = logging.getLogger(__name__)


async def supabase_keepalive_loop(pool: asyncpg.Pool, interval_seconds: float) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await pool.fetchval("select 1")
            logger.info("Supabase keep-alive ping OK")
        except Exception:
            logger.exception("Supabase keep-alive ping failed")
