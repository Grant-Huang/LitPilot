from collections.abc import AsyncIterator
from typing import Optional

from openai import AsyncOpenAI

from app.llm.base import BaseLLM, LLMConfig, LLMMessage, LLMResponse
from app.llm.http_client import get_async_client


class OpenAILLM(BaseLLM):
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            http_client=get_async_client(),
        )

    def _default_model(self) -> str:
        defaults = {
            "openai": "gpt-4o-mini",
            "zhipu": "glm-4-flash",
            "alibaba": "qwen-turbo",
            "qwen": "qwen-plus",
            "deepseek": "deepseek-chat",
            "minimax_intl": "MiniMax-Text-01",
        }
        return self.config.model or defaults.get(self.config.provider, "gpt-4o-mini")

    def _build_messages(
        self,
        messages: list[LLMMessage],
        system: Optional[str],
    ) -> list[dict]:
        msgs: list[dict] = []
        if system:
            msgs.append({"role": "system", "content": system})
        for m in messages:
            msgs.append({"role": m.role, "content": m.content})
        return msgs

    async def chat(
        self,
        messages: list[LLMMessage],
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> LLMResponse:
        model = self._default_model()
        resp = await self._client.chat.completions.create(
            model=model,
            messages=self._build_messages(messages, system),
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return LLMResponse(
            content=resp.choices[0].message.content or "",
            model=model,
            provider=self.config.provider,
            input_tokens=resp.usage.prompt_tokens if resp.usage else None,
            output_tokens=resp.usage.completion_tokens if resp.usage else None,
        )

    async def chat_stream(
        self,
        messages: list[LLMMessage],
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> AsyncIterator[str]:
        model = self._default_model()
        stream = await self._client.chat.completions.create(
            model=model,
            messages=self._build_messages(messages, system),
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta
