"""Debounce aggregation: fast consecutive messages from the same user are combined
into a single AI request (TZ v1.1 p.20.1). The window timer restarts on every new
message; the flush fires only after N seconds of silence."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

FlushCallback = Callable[[int, list[Any]], Awaitable[None]]


class DebounceAggregator:
    def __init__(self, window_seconds: float):
        self._window_seconds = window_seconds
        self._buffers: dict[int, list[Any]] = defaultdict(list)
        self._tasks: dict[int, asyncio.Task] = {}

    async def add(self, user_id: int, payload: Any, flush: FlushCallback) -> None:
        self._buffers[user_id].append(payload)

        existing = self._tasks.get(user_id)
        if existing and not existing.done():
            existing.cancel()

        self._tasks[user_id] = asyncio.create_task(self._wait_and_flush(user_id, flush))

    async def _wait_and_flush(self, user_id: int, flush: FlushCallback) -> None:
        try:
            await asyncio.sleep(self._window_seconds)
        except asyncio.CancelledError:
            return

        messages = self._buffers.pop(user_id, [])
        self._tasks.pop(user_id, None)
        if not messages:
            return
        try:
            await flush(user_id, messages)
        except Exception:
            logger.exception("debounce flush failed for user_id=%s", user_id)
