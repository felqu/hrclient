from __future__ import annotations

import asyncio
import inspect
import os
from dataclasses import dataclass
from typing import Any, AsyncIterator, Iterable, Literal
from urllib.parse import urlsplit

from dotenv import load_dotenv
from openai import OpenAI
from zai import ZaiClient
load_dotenv()


Provider = Literal["zai", "nvidia"]
Message = dict[str, str]


@dataclass(slots=True)
class LLMChunk:
    """Один чанк стрима: обычный контент + reasoning (chain-of-thought)."""
    content: str = ""
    reasoning: str = ""

    def is_empty(self) -> bool:
        return not self.content and not self.reasoning


def _next_or_none(it) -> Any | None:
    try:
        return next(it)
    except StopIteration:
        return None


class LLMClient:


    _PROVIDERS: dict[str, dict[str, Any]] = {
        "zai": {
            "api_key_env": "Z_AI_API_KEY",
            "base_url_env": None,
        },
        "nvidia": {
            "api_key_env": "NVIDIA_API_KEY",
            "base_url_env": "NVIDIA_BASE_URL",
            "default_base_url": "https://integrate.api.nvidia.com/v1",
        },
    }

    def __init__(
        self,
        model: str,
        provider: Provider,
        max_tokens: int = 4096,
        temperature: float = 0.6,
    ) -> None:
        if provider not in self._PROVIDERS:
            raise ValueError(
                f"Неизвестный провайдер: {provider!r}. "
                f"Доступные: {list(self._PROVIDERS)}"
            )

        if not model or not model.strip():
            raise ValueError("Не задана модель LLM. Для NVIDIA задайте NVIDIA_DEEPSEEK.")
        self.model = model.strip()
        self.provider: Provider = provider
        self.max_tokens = max_tokens
        self.temperature = temperature

        self._client = self._build_client()

    # ---------------- инициализация клиента ----------------

    def _build_client(self):
        cfg = self._PROVIDERS[self.provider]
        api_key = os.getenv(cfg["api_key_env"])
        if not api_key:
            raise RuntimeError(
                f"Не задан env-ключ {cfg['api_key_env']} для провайдера {self.provider}"
            )

        if self.provider == "zai":
            if ZaiClient is not None:
                return ZaiClient(api_key=api_key)
            if ZaiClient is None:
                raise RuntimeError(
                    "Пакет `zai` не установлен. `pip install zai-sdk` (или аналог)."
                )
            # fallback: синхронный клиент, будем крутить в отдельном потоке
            return ZaiClient(api_key=api_key)

        if self.provider == "nvidia":
            base_url = (os.getenv(cfg["base_url_env"]) or cfg["default_base_url"]).strip()
            parsed = urlsplit(base_url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise ValueError(
                    "NVIDIA_BASE_URL должен быть полным HTTP(S) URL, "
                    "например https://integrate.api.nvidia.com/v1"
                )
            return OpenAI(base_url=base_url, api_key=api_key)

        raise ValueError(self.provider)

    # ---------------- контекстный менеджер ----------------

    async def __aenter__(self) -> "AsyncLLMClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Закрываем транспорт, если SDK это поддерживает."""
        close = getattr(self._client, "close", None)
        if close is None:
            return
        result = close()
        if inspect.isawaitable(result):
            await result

    # ---------------- основной API ----------------

    async def stream(
        self,
        messages: Iterable[Message],
        *,
        extra: dict[str, Any] | None = None,
    ) -> AsyncIterator[LLMChunk]:
        """Стримит ответ, отдавая LLMChunk(content=..., reasoning=...)."""
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": list(messages),
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": True,
        }

        # Провайдер-специфичные опции
        if self.provider == "zai":
            kwargs["thinking"] = {"type": "enabled"}
        elif self.provider == "nvidia":
            kwargs["top_p"] = 1
            kwargs["seed"] = 42

        if extra:
            kwargs.update(extra)

        response = self._client.chat.completions.create(**kwargs)

        # Асинхронный клиент вернёт awaitable (корутину), sync — сразу iterator.
        if inspect.isawaitable(response):
            response = await response

        if hasattr(response, "__aiter__"):
            async for raw in response:
                chunk = self._to_chunk(raw)
                if not chunk.is_empty():
                    yield chunk
            return

        # Синхронный стрим (например, старый ZaiClient) — тянем чанки в thread-pool
        it = iter(response)
        while True:
            raw = await asyncio.to_thread(_next_or_none, it)
            if raw is None:
                break
            chunk = self._to_chunk(raw)
            if not chunk.is_empty():
                yield chunk

    async def complete(
        self,
        messages: Iterable[Message],
        *,
        extra: dict[str, Any] | None = None,
    ) -> str:
        """Возвращает только финальный текстовый ответ (без reasoning)."""
        parts: list[str] = []
        async for chunk in self.stream(messages, extra=extra):
            if chunk.content:
                parts.append(chunk.content)
        return "".join(parts)

    # ---------------- парсинг чанка ----------------

    @staticmethod
    def _to_chunk(raw: Any) -> LLMChunk:
        choices = getattr(raw, "choices", None) or []
        if not choices:
            return LLMChunk()
        delta = getattr(choices[0], "delta", None)
        if delta is None:
            return LLMChunk()
        return LLMChunk(
            content=getattr(delta, "content", None) or "",
            reasoning=getattr(delta, "reasoning_content", None) or "",
        )
