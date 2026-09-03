"""HTTP clients for Groq (primary) and OpenRouter (fallback), both OpenAI-compatible."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class LLMRequestError(Exception):
    """Raised when a provider call fails (network/timeout/HTTP error)."""


def _raise_with_body(exc: httpx.HTTPStatusError, base_url: str) -> None:
    # str(exc) alone (e.g. "Client error '400 Bad Request' for url ...") never
    # includes *why* — the provider's actual reason is in the response body. Log
    # and surface a snippet of it so a bad request doesn't have to be guessed at.
    body_snippet = exc.response.text[:500]
    logger.warning("LLM HTTP %s from %s: %s", exc.response.status_code, base_url, body_snippet)
    raise LLMRequestError(f"{exc}: {body_snippet}") from exc


class ChatClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 60.0):
        self._base_url = base_url
        self._api_key = api_key
        self._timeout = timeout

    async def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        temperature: float = 0.3,
        max_completion_tokens: int = 4096,
    ) -> str:
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "temperature": temperature,
            "max_completion_tokens": max_completion_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        # gpt-oss spends the completion budget on hidden reasoning first; without
        # a low effort setting JSON mode often dies with json_validate_failed.
        if "gpt-oss" in model:
            payload["reasoning_effort"] = "low"
            payload["include_reasoning"] = False
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(f"{self._base_url}/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            _raise_with_body(exc, self._base_url)
        except httpx.HTTPError as exc:
            raise LLMRequestError(str(exc)) from exc

        data = resp.json()
        try:
            message = data["choices"][0]["message"]
            content = message.get("content") or ""
            if not content:
                # Some reasoning models put the JSON only in `reasoning`.
                content = message.get("reasoning") or ""
            if not content:
                raise LLMRequestError(f"empty LLM content: {data}")
            return content
        except (KeyError, IndexError) as exc:
            raise LLMRequestError(f"unexpected response shape: {data}") from exc


class GroqClient(ChatClient):
    def __init__(self, api_key: str, timeout: float = 60.0):
        super().__init__(GROQ_BASE_URL, api_key, timeout)

    async def transcribe(self, audio_bytes: bytes, filename: str, model: str) -> str:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        files = {"file": (filename, audio_bytes)}
        data = {"model": model, "response_format": "json"}
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{GROQ_BASE_URL}/audio/transcriptions", headers=headers, files=files, data=data
                )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            _raise_with_body(exc, GROQ_BASE_URL)
        except httpx.HTTPError as exc:
            raise LLMRequestError(str(exc)) from exc

        payload = resp.json()
        text = payload.get("text", "")
        return text.strip()


class OpenRouterClient(ChatClient):
    def __init__(self, api_key: str, timeout: float = 30.0):
        super().__init__(OPENROUTER_BASE_URL, api_key, timeout)
