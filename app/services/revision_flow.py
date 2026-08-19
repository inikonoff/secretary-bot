"""Post-completion revision flow (TZ v1.1 p.67-68, AI Specification v1.1 §33)."""

from __future__ import annotations

from app.ai.orchestrator import AIOrchestrator, AIUnavailableError
from app.ai.prompts import REVISION_SYSTEM_PROMPT, build_revision_user_prompt
from app.ai.schemas import RevisionResult
from app.constants import EVENT_FALLBACK_TRIGGERED, EVENT_LLM_ERROR, EVENT_REVISION_CREATED
from app.db.repo import Repo


class RevisionFlowService:
    def __init__(self, repo: Repo, orchestrator: AIOrchestrator):
        self.repo = repo
        self.orchestrator = orchestrator

    async def analyze(self, application: dict, raw_text: str) -> RevisionResult:
        previous = await self.repo.revisions.list_for_application(application["id"])
        previous_summary = [{"ai_summary": r["ai_summary"], "status": r["status"]} for r in previous]
        user_prompt = build_revision_user_prompt(application.get("project_context") or {}, previous_summary, raw_text)

        try:
            result, used_fallback = await self.orchestrator.process_revision(REVISION_SYSTEM_PROMPT, user_prompt)
        except AIUnavailableError as exc:
            await self.repo.events.log(
                EVENT_LLM_ERROR, application_id=application["id"], user_id=application["user_id"],
                payload={"error": str(exc), "stage": "revision"},
            )
            raise

        if used_fallback:
            await self.repo.events.log(
                EVENT_FALLBACK_TRIGGERED, application_id=application["id"], user_id=application["user_id"],
                payload={"stage": "revision"},
            )

        return result

    async def confirm(self, application_id: int, user_id: int, raw_text: str, client_message: str, ai_summary: str) -> dict:
        revision = await self.repo.revisions.create(application_id, user_id, raw_text, client_message, ai_summary)
        await self.repo.events.log(
            EVENT_REVISION_CREATED, application_id=application_id, user_id=user_id,
            payload={"revision_id": revision["id"]},
        )
        return revision
