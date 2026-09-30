from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    api_key: str | None
    model: str
    temperature: float = 0.2


class LLMProvider(ABC):
    @abstractmethod
    async def complete(self, *, system: str, prompt: str, json_mode: bool = False) -> str:
        """Return generated text; caller owns validation of structured output."""


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    async def complete(self, *, system: str, prompt: str, json_mode: bool = False) -> str:
        headers = {"Authorization": f"Bearer {self.config.api_key}"} if self.config.api_key else {}
        payload = {
            "model": self.config.model,
            "temperature": self.config.temperature,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        async with httpx.AsyncClient(base_url=self.config.base_url, timeout=60) as client:
            response = await client.post("/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


class OllamaProvider(OpenAICompatibleProvider):
    """Ollama with its OpenAI-compatible `/v1` endpoint."""


class LlamaCppProvider(OpenAICompatibleProvider):
    """llama.cpp server in OpenAI-compatible mode; native /completion can be another adapter."""


class CodexStyleProvider(OpenAICompatibleProvider):
    """Adapter placeholder for an approved Codex-compatible endpoint."""


class FallbackLLMProvider(LLMProvider):
    def __init__(self, providers: list[LLMProvider]) -> None:
        self.providers = providers

    async def complete(self, *, system: str, prompt: str, json_mode: bool = False) -> str:
        last_error: Exception | None = None
        for provider in self.providers:
            try:
                return await provider.complete(system=system, prompt=prompt, json_mode=json_mode)
            except (httpx.HTTPError, KeyError, ValueError) as error:
                last_error = error
        raise RuntimeError("All LLM fallback providers failed") from last_error
