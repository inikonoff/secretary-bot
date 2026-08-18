"""Technical rate limiting, independent from the interview clarifying-questions limit
(TZ v1.1 p.20.2). Fires before any LLM call. In-memory sliding window — fine for a
single Render instance; move to Redis if the bot is ever scaled horizontally."""

from __future__ import annotations

import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, max_messages: int, window_seconds: float):
        self._max_messages = max_messages
        self._window_seconds = window_seconds
        self._hits: dict[int, deque[float]] = defaultdict(deque)

    def allow(self, user_id: int) -> bool:
        now = time.monotonic()
        bucket = self._hits[user_id]
        while bucket and now - bucket[0] > self._window_seconds:
            bucket.popleft()
        if len(bucket) >= self._max_messages:
            return False
        bucket.append(now)
        return True
