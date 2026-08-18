"""HTTP clients for Groq (primary) and OpenRouter (fallback), both OpenAI-compatible."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class LLMRequestError(Exception):
    """Raised when a provider call fails (network/timeout/HTTP error)."""


class ChatClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 30.0):
        self._base_url = base_url
        self._api_key = api_key
        self._timeout = timeout

    async def chat_json(self, system_prompt: str, user_prompt: str, model: str, temperature: float = 0.3) -> str:
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(f"{self._base_url}/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMRequestError(str(exc)) from exc

        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise LLMRequestError(f"unexpected response shape: {data}") from exc


class GroqClient(ChatClient):
    def __init__(self, api_key: str, timeout: float = 30.0):
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
        except httpx.HTTPError as exc:
            raise LLMRequestError(str(exc)) from exc

        payload = resp.json()
        text = payload.get("text", "")
        return text.strip()


class OpenRouterClient(ChatClient):
    def __init__(self, api_key: str, timeout: float = 30.0):
        super().__init__(OPENROUTER_BASE_URL, api_key, timeout)
