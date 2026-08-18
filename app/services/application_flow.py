"""Core state-machine orchestration tying DB + AI Orchestrator together
(TZ v1.1 p.57 "AI Orchestrator" layer + p.58 State Machine).

Deadline handling note: the TZ (p.16) asks a single free-text deadline
question "after the AI interview" but the state diagram in p.58 doesn't carve
out a dedicated slot for it. We insert an explicit WAITING_DEADLINE state
between the adaptive interview and the Understanding/confirmation screen:
the question is asked exactly once, right when the interview model first
reaches action=understanding, and the very next user message is stored
verbatim as the answer (no re-asking, per p.16)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Literal

from app.ai.orchestrator import AIOrchestrator, AIUnavailableError
from app.ai.prompts import (
    DEADLINE_PARSE_SYSTEM_PROMPT,
    INTERVIEW_SYSTEM_PROMPT,
    build_interview_user_prompt,
)
from app.constants import (
    EVENT_FALLBACK_TRIGGERED,
    EVENT_LLM_ERROR,
    EVENT_POSSIBLE_ABUSE,
    MESSAGE_SENDER_ASSISTANT,
    MESSAGE_TYPE_TEXT,
    STATE_INTERVIEW,
    STATE_WAITING_CONFIRMATION,
    STATE_WAITING_DEADLINE,
    STATE_WAITING_INITIAL_DESCRIPTION,
)
from app.db.repo import Repo

logger = logging.getLogger(__name__)

ABANDON_MESSAGE = (
    "Похоже, у нас не получается прийти к взаимопониманию по этому вопросу. "
    "Пожалуйста, создайте новую заявку через /new и попробуйте описать задачу иначе — "
    "так будет проще разобраться."
)

AI_ERROR_MESSAGE = (
    "Сейчас не получается обработать сообщение — сервис временно недоступен. "
    "Пожалуйста, попробуйте ещё раз через пару минут."
)


@dataclass
class InterviewOutcome:
    kind: Literal["ask", "ask_deadline", "understanding", "abandoned"]
    message: str
    language: str | None = None


class ApplicationFlowService:
    def __init__(self, repo: Repo, orchestrator: AIOrchestrator, settings):
        self.repo = repo
        self.orchestrator = orchestrator
        self.settings = settings

    async def create_application(self, user: dict) -> dict:
        application = await self.repo.applications.create(user["id"], STATE_WAITING_INITIAL_DESCRIPTION)
        await self.repo.events.log("application_created", application_id=application["id"], user_id=user["id"])
        return application

    async def cancel_application(self, application: dict) -> None:
        await self.repo.applications.cancel(application["id"])
        await self.repo.events.log("application_cancelled", application_id=application["id"], user_id=application["user_id"])

    async def _run_interview_and_apply(self, application: dict, latest_text: str, is_add_info_round: bool) -> InterviewOutcome:
        recent = await self.repo.messages.recent_for_application(application["id"], limit=6)
        user_prompt = build_interview_user_prompt(
            project_context=application.get("project_context") or {},
            recent_messages=recent,
            latest_user_message=latest_text,
            clarifying_questions_count=application["clarifying_questions_count"],
            add_information_count=application["add_info_count"],
            is_add_information_round=is_add_info_round,
        )

        try:
            result, used_fallback = await self.orchestrator.run_interview_step(INTERVIEW_SYSTEM_PROMPT, user_prompt)
        except AIUnavailableError as exc:
            await self.repo.events.log(
                EVENT_LLM_ERROR, application_id=application["id"], user_id=application["user_id"],
                payload={"error": str(exc), "stage": "interview"},
            )
            raise

        if used_fallback:
            await self.repo.events.log(
                EVENT_FALLBACK_TRIGGERED, application_id=application["id"], user_id=application["user_id"],
                payload={"stage": "interview"},
            )

        await self.repo.applications.update_project_context(application["id"], result.project_context.model_dump())
        await self.repo.messages.add(
            application["id"], MESSAGE_SENDER_ASSISTANT, MESSAGE_TYPE_TEXT, result.client_message, result.language, None
        )
        await self.repo.users.set_language(application["user_id"], result.language)

        if result.action == "ask":
            topic = result.question.topic if result.question else None
            prev_topic = application.get("current_question_topic")
            same_topic_retry_count = (application.get("same_topic_retry_count") or 0) + 1 if topic and topic == prev_topic else 0
            await self.repo.applications.update_topic_tracking(application["id"], topic, same_topic_retry_count)

            if same_topic_retry_count >= self.settings.same_topic_abandon_threshold:
                await self.repo.applications.set_flagged_abuse(application["id"])
                await self.repo.applications.cancel(application["id"])
                await self.repo.events.log(
                    EVENT_POSSIBLE_ABUSE, application_id=application["id"], user_id=application["user_id"],
                    payload={"topic": topic},
                )
                return InterviewOutcome(kind="abandoned", message=ABANDON_MESSAGE, language=result.language)

            await self.repo.applications.increment_clarifying_questions_count(application["id"])
            await self.repo.applications.update_state(application["id"], STATE_INTERVIEW)
            return InterviewOutcome(kind="ask", message=result.client_message, language=result.language)

        # action in ("understanding", "wait_input", "error") — treat unknown/defensive actions as understanding
        await self.repo.applications.update_topic_tracking(application["id"], None, 0)

        if application.get("deadline_text") is None:
            await self.repo.applications.set_pending_understanding_message(application["id"], result.client_message)
            await self.repo.applications.update_state(application["id"], STATE_WAITING_DEADLINE)
            return InterviewOutcome(kind="ask_deadline", message=result.client_message, language=result.language)

        await self.repo.applications.update_client_understanding(application["id"], result.client_message)
        await self.repo.applications.update_state(application["id"], STATE_WAITING_CONFIRMATION)
        return InterviewOutcome(kind="understanding", message=result.client_message, language=result.language)

    async def process_initial_description(self, application: dict, text: str) -> InterviewOutcome:
        return await self._run_interview_and_apply(application, text, is_add_info_round=False)

    async def process_interview_message(self, application: dict, text: str) -> InterviewOutcome:
        return await self._run_interview_and_apply(application, text, is_add_info_round=False)

    async def process_add_information_message(self, application: dict, text: str) -> InterviewOutcome:
        return await self._run_interview_and_apply(application, text, is_add_info_round=True)

    async def process_deadline_answer(self, application: dict, text: str) -> InterviewOutcome:
        deadline_text = text
        try:
            user_prompt = json.dumps({"user_answer": text}, ensure_ascii=False)
            result, used_fallback = await self.orchestrator.parse_deadline(DEADLINE_PARSE_SYSTEM_PROMPT, user_prompt)
            deadline_text = result.deadline_text or text
            if used_fallback:
                await self.repo.events.log(
                    EVENT_FALLBACK_TRIGGERED, application_id=application["id"], user_id=application["user_id"],
                    payload={"stage": "deadline_parse"},
                )
        except AIUnavailableError as exc:
            logger.warning("deadline parse failed, storing raw text: %s", exc)

        await self.repo.applications.set_deadline_text(application["id"], deadline_text)

        pending_message = application.get("pending_understanding_message") or ""
        await self.repo.applications.update_client_understanding(application["id"], pending_message)
        await self.repo.applications.set_pending_understanding_message(application["id"], None)
        await self.repo.applications.update_state(application["id"], STATE_WAITING_CONFIRMATION)

        return InterviewOutcome(kind="understanding", message=pending_message)

    def can_add_information(self, application: dict) -> bool:
        return application["add_info_count"] < self.settings.max_add_info_cycles
