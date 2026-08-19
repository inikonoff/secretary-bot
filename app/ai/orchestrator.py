"""AI Orchestrator: structured calls to Groq with JSON validation, repair and OpenRouter fallback
(TZ v1.1 p.38/p.57, AI Specification v1.1 §12-13, §27, §38 semantics)."""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel, ValidationError

from app.ai.clients import ChatClient, GroqClient, LLMRequestError, OpenRouterClient
from app.ai.prompts import build_repair_prompt
from app.ai.schemas import DeadlineParseResult, FinalTZResult, InterviewResult, RevisionResult

logger = logging.getLogger(__name__)


class AIUnavailableError(Exception):
    """Both Groq and the OpenRouter fallback failed to produce a valid structured response."""


class AIOrchestrator:
    def __init__(
        self,
        groq_api_key: str,
        openrouter_api_key: str,
        groq_model_interview: str,
        groq_model_final: str,
        groq_whisper_model: str,
        openrouter_model_interview: str,
        openrouter_model_final: str,
    ):
        self._groq = GroqClient(groq_api_key)
        self._openrouter = OpenRouterClient(openrouter_api_key) if openrouter_api_key else None
        self._groq_model_interview = groq_model_interview
        self._groq_model_final = groq_model_final
        self._groq_whisper_model = groq_whisper_model
        self._openrouter_model_interview = openrouter_model_interview
        self._openrouter_model_final = openrouter_model_final

    async def _call_with_repair(
        self, client: ChatClient, model: str, system_prompt: str, user_prompt: str, schema: type[BaseModel]
    ) -> BaseModel:
        raw = await client.chat_json(system_prompt, user_prompt, model)
        try:
            return schema.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValidationError) as exc:
            repair_prompt = build_repair_prompt(raw, str(exc))
            raw2 = await client.chat_json(system_prompt, repair_prompt, model)
            return schema.model_validate(json.loads(raw2))

    async def _structured_call(
        self, system_prompt: str, user_prompt: str, schema: type[BaseModel], interview: bool
    ) -> tuple[BaseModel, bool]:
        groq_model = self._groq_model_interview if interview else self._groq_model_final
        try:
            result = await self._call_with_repair(self._groq, groq_model, system_prompt, user_prompt, schema)
            return result, False
        except (LLMRequestError, json.JSONDecodeError, ValidationError) as exc:
            logger.warning("Groq call failed (%s), falling back to OpenRouter", exc)

        if self._openrouter is None:
            raise AIUnavailableError("Groq failed and no OpenRouter fallback is configured")

        openrouter_model = self._openrouter_model_interview if interview else self._openrouter_model_final
        try:
            result = await self._call_with_repair(
                self._openrouter, openrouter_model, system_prompt, user_prompt, schema
            )
            return result, True
        except (LLMRequestError, json.JSONDecodeError, ValidationError) as exc:
            raise AIUnavailableError(f"both Groq and OpenRouter failed: {exc}") from exc

    async def run_interview_step(self, system_prompt: str, user_prompt: str) -> tuple[InterviewResult, bool]:
        result, used_fallback = await self._structured_call(system_prompt, user_prompt, InterviewResult, True)
        return result, used_fallback  # type: ignore[return-value]

    async def generate_final_tz(self, system_prompt: str, user_prompt: str) -> tuple[FinalTZResult, bool]:
        result, used_fallback = await self._structured_call(system_prompt, user_prompt, FinalTZResult, False)
        return result, used_fallback  # type: ignore[return-value]

    async def parse_deadline(self, system_prompt: str, user_prompt: str) -> tuple[DeadlineParseResult, bool]:
        result, used_fallback = await self._structured_call(system_prompt, user_prompt, DeadlineParseResult, True)
        return result, used_fallback  # type: ignore[return-value]

    async def process_revision(self, system_prompt: str, user_prompt: str) -> tuple[RevisionResult, bool]:
        # Revisions use the lighter interview model (gpt-oss-20b), not the final-TZ model
        # (AI Specification v1.1 §33.1) — single pass, no add-info cycle.
        result, used_fallback = await self._structured_call(system_prompt, user_prompt, RevisionResult, True)
        return result, used_fallback  # type: ignore[return-value]

    async def transcribe_voice(self, audio_bytes: bytes, filename: str) -> str:
        try:
            return await self._groq.transcribe(audio_bytes, filename, self._groq_whisper_model)
        except LLMRequestError as exc:
            raise AIUnavailableError(f"Whisper transcription failed: {exc}") from exc
