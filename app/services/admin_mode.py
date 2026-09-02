"""Lets the single admin flip their own Telegram account into a full simulation
of the client experience, to test the interview flow without a second account.

In-memory and per-process: a restart resets everyone back to Admin mode — the
safer default, so a redeploy never silently leaves the real admin unable to see
new applications because they forgot they were "logged in" as a test client."""

from __future__ import annotations

ADMIN_MODE = "admin"
USER_MODE = "user"


class AdminModeRegistry:
    def __init__(self):
        self._modes: dict[int, str] = {}

    def get(self, telegram_id: int) -> str:
        return self._modes.get(telegram_id, ADMIN_MODE)

    def set(self, telegram_id: int, mode: str) -> None:
        self._modes[telegram_id] = mode
