"""Per-(user_id, application_id) lock so concurrent callbacks/messages on the same
application are processed strictly sequentially (TZ v1.1 p.30)."""

from __future__ import annotations

import asyncio
from collections import defaultdict


class LockRegistry:
    def __init__(self):
        self._locks: dict[tuple[int, int], asyncio.Lock] = defaultdict(asyncio.Lock)

    def get(self, user_id: int, application_id: int) -> asyncio.Lock:
        return self._locks[(user_id, application_id)]
