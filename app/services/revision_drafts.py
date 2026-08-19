"""In-memory scratch space for a client's revision description while composing it
(TZ v1.1 p.68.2). Nothing is persisted to `revisions` until the client presses
"✅ Верно" — the flow is intentionally a single lightweight pass (AI Spec §33.4),
so, unlike the main interview, there's no DB-backed intermediate state to protect
across a restart; a lost draft simply means the client re-describes the revision."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RevisionDraft:
    application_id: int
    raw_text: str = ""
    client_message: str = ""
    ai_summary: str = ""
    language: str | None = None
    awaiting_confirmation: bool = False


class RevisionDraftRegistry:
    def __init__(self):
        self._drafts: dict[int, RevisionDraft] = {}

    def start(self, user_id: int, application_id: int) -> None:
        self._drafts[user_id] = RevisionDraft(application_id=application_id)

    def get(self, user_id: int) -> RevisionDraft | None:
        return self._drafts.get(user_id)

    def update(self, user_id: int, **fields) -> None:
        draft = self._drafts.get(user_id)
        if draft is None:
            return
        for key, value in fields.items():
            setattr(draft, key, value)

    def pop(self, user_id: int) -> RevisionDraft | None:
        return self._drafts.pop(user_id, None)
