"""
LLM 클라이언트 추상화 레이어.

config.llm_backend 값에 따라 Claude(Anthropic) 또는 Ollama(OpenAI 호환) 중 하나를
반환한다. 에이전트 코드는 LLMClient.chat()만 호출하면 된다.

지원 백엔드:
  claude  — Anthropic API (기본값, claude-sonnet-4-6 등)
  ollama  — Ollama 로컬 서버 (qwen3, llama3 등 OpenAI 호환 엔드포인트 사용)
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

# <think>...</think> 블록 제거 — Qwen3 등 사고 모드 모델 출력 정제용
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _strip_thinking(text: str) -> str:
    return _THINK_RE.sub("", text).strip()


class LLMClient(ABC):
    """에이전트가 사용하는 LLM 호출 인터페이스."""

    @abstractmethod
    async def chat(self, *, system: str, user: str, max_tokens: int) -> str:
        """system 프롬프트와 user 메시지를 받아 모델 응답 텍스트를 반환한다."""
        ...


class ClaudeClient(LLMClient):
    """Anthropic Claude API 클라이언트."""

    def __init__(self, api_key: str, model: str) -> None:
        import anthropic
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def chat(self, *, system: str, user: str, max_tokens: int) -> str:
        import anthropic
        msg = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return msg.content[0].text.strip()


class OllamaClient(LLMClient):
    """Ollama OpenAI 호환 엔드포인트 클라이언트.

    Qwen3처럼 <think> 블록을 출력하는 모델은 자동으로 사고 영역을 제거한다.
    think=False 옵션으로 사고 모드 자체를 비활성화할 수도 있다.
    """

    def __init__(self, base_url: str, model: str, think: bool = False) -> None:
        from openai import AsyncOpenAI
        self._client = AsyncOpenAI(
            base_url=f"{base_url.rstrip('/')}/v1",
            api_key="ollama",   # Ollama는 인증 불필요, 임의 값
        )
        self._model = model
        self._think = think

    async def chat(self, *, system: str, user: str, max_tokens: int) -> str:
        kwargs: dict = {}
        if not self._think:
            # Ollama Qwen3 사고 모드 비활성화
            kwargs["extra_body"] = {"think": False}

        resp = await self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            **kwargs,
        )
        text = resp.choices[0].message.content or ""
        # 사고 모드가 활성화된 경우에도 <think> 태그가 포함될 수 있으므로 정제
        return _strip_thinking(text)


def make_llm_client(settings) -> LLMClient:
    """settings.llm_backend 값에 따라 적절한 LLMClient를 반환한다."""
    backend = settings.llm_backend.lower()

    if backend == "ollama":
        logger.info(
            "LLM backend: Ollama — url=%s model=%s think=%s",
            settings.ollama_url, settings.ollama_model, settings.ollama_think,
        )
        return OllamaClient(
            base_url=settings.ollama_url,
            model=settings.ollama_model,
            think=settings.ollama_think,
        )

    if backend == "claude":
        logger.info("LLM backend: Claude — model=%s", settings.claude_model)
        return ClaudeClient(
            api_key=settings.anthropic_api_key,
            model=settings.claude_model,
        )

    raise ValueError(
        f"Unknown llm_backend: {backend!r}. Choose 'claude' or 'ollama'."
    )
