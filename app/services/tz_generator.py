"""Final TZ generation: gpt-oss-120b call + quality gate + FINALIZED transition
(AI Specification v1.1 §12, §24-29)."""

from __future__ import annotations

import logging

from app.ai.orchestrator import AIOrchestrator, AIUnavailableError
from app.ai.prompts import FINAL_TZ_SYSTEM_PROMPT, build_final_tz_user_prompt
from app.ai.schemas import FinalTZResult
from app.constants import EVENT_FALLBACK_TRIGGERED, EVENT_LLM_ERROR
from app.db.repo import Repo
from app.services.tz_quality import check_tz_quality

logger = logging.getLogger(__name__)

MAX_QUALITY_RETRIES = 2


class TZGenerationError(Exception):
    """Raised when the final TZ could not be produced after retries — the
    application must NOT be moved to FINALIZED (AI spec §27)."""


class TZGeneratorService:
    def __init__(self, repo: Repo, orchestrator: AIOrchestrator):
        self.repo = repo
        self.orchestrator = orchestrator

    async def generate_and_finalize(self, application: dict) -> FinalTZResult:
        recent = await self.repo.messages.all_for_application(application["id"])
        user_prompt = build_final_tz_user_prompt(
            client_understanding=application.get("client_understanding_text") or "",
            project_context=application.get("project_context") or {},
            recent_messages=recent[-20:],
            deadline_text=application.get("deadline_text"),
        )

        result: FinalTZResult | None = None
        problems: list[str] = []

        for attempt in range(1, MAX_QUALITY_RETRIES + 1):
            try:
                candidate, used_fallback = await self.orchestrator.generate_final_tz(FINAL_TZ_SYSTEM_PROMPT, user_prompt)
            except AIUnavailableError as exc:
                await self.repo.events.log(
                    EVENT_LLM_ERROR, application_id=application["id"], user_id=application["user_id"],
                    payload={"error": str(exc), "stage": "final_tz", "attempt": attempt},
                )
                raise TZGenerationError(str(exc)) from exc

            if used_fallback:
                await self.repo.events.log(
                    EVENT_FALLBACK_TRIGGERED, application_id=application["id"], user_id=application["user_id"],
                    payload={"stage": "final_tz", "attempt": attempt},
                )

            problems = check_tz_quality(candidate)
            if not problems:
                result = candidate
                break

            logger.warning("TZ quality check failed (attempt %s): %s", attempt, problems)
            user_prompt = (
                user_prompt
                + "\n\nПредыдущая попытка не прошла проверку качества, исправь следующее: "
                + "; ".join(problems)
            )

        if result is None:
            await self.repo.events.log(
                EVENT_LLM_ERROR, application_id=application["id"], user_id=application["user_id"],
                payload={"stage": "final_tz_quality_gate", "problems": problems},
            )
            raise TZGenerationError(f"quality gate failed after {MAX_QUALITY_RETRIES} attempts: {problems}")

        tz_path = f"TZ_{application['id']}.md"
        await self.repo.applications.finalize(application["id"], tz_path, result.technical_specification_markdown)
        await self.repo.events.log("application_finalized", application_id=application["id"], user_id=application["user_id"])
        return result
