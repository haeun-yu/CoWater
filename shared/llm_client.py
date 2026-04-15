"""
LLM 클라이언트 추상화 레이어.

config.llm_backend 값에 따라 Claude(Anthropic) 또는 Ollama(OpenAI 호환) 중 하나를
반환한다. API key가 없으면 FallbackClient가 반환되어 rule 기반 권고문을 생성한다.

각 클라이언트는 타임아웃과 지수 백오프 재시도를 내장한다:
- Claude: timeout=60s, 최대 3회 재시도 (네트워크 오류/타임아웃에 한함)
- Ollama/vLLM: timeout=120s, 최대 2회 재시도 (로컬 서버 응답 지연 고려)
"""

from __future__ import annotations

import asyncio
import logging
import re
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _strip_thinking(text: str) -> str:
    return _THINK_RE.sub("", text).strip()


async def _retry_chat(call, *, max_attempts: int, base_delay: float) -> str:
    """네트워크 오류/타임아웃에 한해 지수 백오프 재시도.

    비즈니스 오류(잘못된 요청 등)는 재시도하지 않고 즉시 전파한다.
    """
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return await call()
        except (TimeoutError, OSError, ConnectionError) as exc:
            last_exc = exc
            if attempt < max_attempts - 1:
                wait = base_delay * (2 ** attempt)
                logger.warning(
                    "LLM call failed (%s), retrying in %.1fs (attempt %d/%d)",
                    type(exc).__name__, wait, attempt + 1, max_attempts,
                )
                await asyncio.sleep(wait)
    raise last_exc  # type: ignore[misc]


class LLMClient(ABC):
    @abstractmethod
    async def chat(self, *, system: str, user: str, max_tokens: int) -> str: ...

    async def generate(self, prompt: str, max_tokens: int = 2048) -> str:
        """단순 생성 — system message 없이 prompt만 사용"""
        return await self.chat(system="", user=prompt, max_tokens=max_tokens)

    async def chat_stream(self, *, system: str, user: str, max_tokens: int):
        """청크 단위로 텍스트를 yield하는 스트리밍 채팅. 기본 구현은 전체 응답을 한 번에 반환."""
        yield await self.chat(system=system, user=user, max_tokens=max_tokens)

    @property
    def is_available(self) -> bool:
        return True

    @property
    def model_name(self) -> str:
        return "unknown"


class ClaudeClient(LLMClient):
    def __init__(self, api_key: str, model: str, *, timeout: float = 60.0, max_attempts: int = 3, base_delay: float = 1.0) -> None:
        import anthropic
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model
        self._TIMEOUT = timeout
        self._MAX_ATTEMPTS = max_attempts
        self._BASE_DELAY = base_delay

    @property
    def model_name(self) -> str:
        return f"claude/{self._model}"

    async def chat(self, *, system: str, user: str, max_tokens: int) -> str:
        async def _call() -> str:
            async with asyncio.timeout(self._TIMEOUT):
                msg = await self._client.messages.create(
                    model=self._model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
            return msg.content[0].text.strip()

        return await _retry_chat(
            _call, max_attempts=self._MAX_ATTEMPTS, base_delay=self._BASE_DELAY
        )

    async def chat_stream(self, *, system: str, user: str, max_tokens: int):
        """Claude 스트리밍 API — 청크 단위로 텍스트를 yield한다."""
        async with asyncio.timeout(self._TIMEOUT):
            async with self._client.messages.stream(
                model=self._model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            ) as stream:
                async for chunk in stream.text_stream:
                    yield chunk


class OllamaClient(LLMClient):
    def __init__(self, base_url: str, model: str, think: bool = False, *, timeout: float = 120.0, max_attempts: int = 2, base_delay: float = 2.0) -> None:
        self._TIMEOUT = timeout
        self._MAX_ATTEMPTS = max_attempts
        self._BASE_DELAY = base_delay
        from openai import AsyncOpenAI
        self._client = AsyncOpenAI(
            base_url=f"{base_url.rstrip('/')}/v1",
            api_key="ollama",
        )
        self._model = model
        self._think = think

    @property
    def model_name(self) -> str:
        return f"ollama/{self._model}"

    async def chat(self, *, system: str, user: str, max_tokens: int) -> str:
        kwargs: dict = {}
        if not self._think:
            kwargs["extra_body"] = {"think": False}

        async def _call() -> str:
            async with asyncio.timeout(self._TIMEOUT):
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
            return _strip_thinking(text)

        return await _retry_chat(
            _call, max_attempts=self._MAX_ATTEMPTS, base_delay=self._BASE_DELAY
        )

    async def chat_stream(self, *, system: str, user: str, max_tokens: int):
        """Ollama 스트리밍 API — 청크 단위로 텍스트를 yield한다."""
        kwargs: dict = {}
        if not self._think:
            kwargs["extra_body"] = {"think": False}

        async with asyncio.timeout(self._TIMEOUT):
            stream = await self._client.chat.completions.create(
                model=self._model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                stream=True,
                **kwargs,
            )
            async for chunk in stream:
                text = chunk.choices[0].delta.content if chunk.choices else None
                if text:
                    yield _strip_thinking(text)


class VllmClient(LLMClient):
    """vLLM 서버 클라이언트 (OpenAI 호환 API).

    vLLM은 OpenAI 호환 엔드포인트를 제공하므로 OllamaClient와 구조가 동일하되,
    think 파라미터 등 Ollama 전용 옵션을 제거한 순수 OpenAI 호환 구현이다.
    """

    def __init__(self, base_url: str, model: str, *, timeout: float = 120.0, max_attempts: int = 2, base_delay: float = 2.0) -> None:
        self._TIMEOUT = timeout
        self._MAX_ATTEMPTS = max_attempts
        self._BASE_DELAY = base_delay
        from openai import AsyncOpenAI
        self._client = AsyncOpenAI(
            base_url=f"{base_url.rstrip('/')}/v1",
            api_key="vllm",  # vLLM은 API key 불필요 — 더미값
        )
        self._model = model

    @property
    def model_name(self) -> str:
        return f"vllm/{self._model}"

    async def chat(self, *, system: str, user: str, max_tokens: int) -> str:
        async def _call() -> str:
            async with asyncio.timeout(self._TIMEOUT):
                resp = await self._client.chat.completions.create(
                    model=self._model,
                    max_tokens=max_tokens,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                )
            return (resp.choices[0].message.content or "").strip()

        return await _retry_chat(
            _call, max_attempts=self._MAX_ATTEMPTS, base_delay=self._BASE_DELAY
        )


class FallbackClient(LLMClient):
    """API key 미설정 시 사용. rule 기반 권고문을 반환."""

    @property
    def is_available(self) -> bool:
        return False

    @property
    def model_name(self) -> str:
        return "fallback/rule-based"

    async def chat(self, *, system: str, user: str, max_tokens: int) -> str:
        # user 메시지에서 핵심 정보 추출해 간단한 권고문 생성
        lines = [l.strip() for l in user.splitlines() if l.strip()]
        summary = " | ".join(lines[:4])
        return (
            f"[AI 분석 불가 — ANTHROPIC_API_KEY 미설정]\n\n"
            f"상황 요약: {summary}\n\n"
            "권고사항:\n"
            "1. 해당 선박의 현재 위치 및 상태를 즉시 확인하십시오.\n"
            "2. 인접 선박 및 VHF Ch.16을 통해 교신을 시도하십시오.\n"
            "3. 필요 시 해양경찰청에 상황을 통보하십시오.\n\n"
            "AI 분석을 활성화하려면 ANTHROPIC_API_KEY 환경변수를 설정하세요."
        )


def make_llm_client(settings) -> LLMClient:
    backend = settings.llm_backend.lower()

    if backend == "ollama":
        logger.info("LLM backend: Ollama — url=%s model=%s", settings.ollama_url, settings.ollama_model)
        return OllamaClient(
            base_url=settings.ollama_url,
            model=settings.ollama_model,
            think=getattr(settings, 'ollama_think', False),
            timeout=settings.local_llm_timeout_sec,
            max_attempts=settings.local_llm_max_attempts,
            base_delay=settings.local_llm_base_delay_sec,
        )

    if backend == "claude":
        if not settings.anthropic_api_key:
            logger.warning(
                "ANTHROPIC_API_KEY가 설정되지 않았습니다. "
                "AI 에이전트는 rule 기반 fallback 권고문을 사용합니다. "
                "환경변수 ANTHROPIC_API_KEY를 설정하면 Claude AI 분석이 활성화됩니다."
            )
            return FallbackClient()
        logger.info("LLM backend: Claude — model=%s", settings.claude_model)
        return ClaudeClient(
            api_key=settings.anthropic_api_key,
            model=settings.claude_model,
            timeout=settings.claude_timeout_sec,
            max_attempts=settings.claude_max_attempts,
            base_delay=settings.claude_base_delay_sec,
        )

    if backend == "vllm":
        logger.info("LLM backend: vLLM — url=%s model=%s", settings.vllm_url, settings.vllm_model)
        return VllmClient(
            base_url=settings.vllm_url,
            model=settings.vllm_model,
            timeout=settings.local_llm_timeout_sec,
            max_attempts=settings.local_llm_max_attempts,
            base_delay=settings.local_llm_base_delay_sec,
        )

    raise ValueError(f"Unknown llm_backend: {backend!r}. Choose 'claude', 'ollama', or 'vllm'.")
