from __future__ import annotations

"""
Shared LLM Client - supports Ollama and other LLM providers

Enhanced with error classification, retry logic, and comprehensive logging.
"""

import asyncio
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
import urllib.error
import urllib.request

try:
    import httpx
except ImportError:
    httpx = None

logger = logging.getLogger(__name__)

# LLM_DEBUG=1 환경변수 설정 시 프롬프트/응답 전문 로깅
_LLM_DEBUG = os.environ.get("LLM_DEBUG", "").strip() in ("1", "true", "yes")
print(f"[llm_client] LLM_DEBUG={'ON' if _LLM_DEBUG else 'OFF'} (env={os.environ.get('LLM_DEBUG', '')})", flush=True)


# ──────────────────────────────────────────────
# Error Classification
# ──────────────────────────────────────────────

class LLMErrorType(Enum):
    """LLM 오류 분류"""
    NETWORK_ERROR = "network_error"          # 연결 실패 (DNS, Connection refused)
    TIMEOUT_ERROR = "timeout_error"          # 응답 지연
    PARSE_ERROR = "parse_error"              # JSON/응답 파싱 실패
    VALIDATION_ERROR = "validation_error"    # 응답 검증 실패 (응답 형식 오류)
    MODEL_ERROR = "model_error"              # 모델 자체 오류 (HTTP 5xx)
    CIRCUIT_BREAKER_OPEN = "circuit_open"    # Circuit breaker 오픈
    UNKNOWN_ERROR = "unknown_error"          # 미분류 오류


@dataclass
class LLMErrorContext:
    """LLM 오류 컨텍스트"""
    error_type: LLMErrorType
    message: str
    original_exception: Optional[Exception] = None
    attempt_number: int = 1
    max_attempts: int = 3
    recovery_strategy: str = "skip"  # "retry", "fallback", "skip", "manual"
    timestamp: str = ""
    elapsed_ms: int = 0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def is_retryable(self) -> bool:
        """재시도 가능한가?"""
        retryable_types = {
            LLMErrorType.NETWORK_ERROR,
            LLMErrorType.TIMEOUT_ERROR,
            LLMErrorType.MODEL_ERROR,
        }
        return (
            self.error_type in retryable_types
            and self.attempt_number < self.max_attempts
        )

    def to_dict(self) -> dict[str, Any]:
        """Dict 직렬화"""
        return {
            "error_type": self.error_type.value,
            "message": self.message,
            "attempt_number": self.attempt_number,
            "max_attempts": self.max_attempts,
            "recovery_strategy": self.recovery_strategy,
            "timestamp": self.timestamp,
            "elapsed_ms": self.elapsed_ms,
            "is_retryable": self.is_retryable(),
        }


class LLMClient(ABC):
    """Abstract LLM Client interface with error handling"""

    @abstractmethod
    async def generate(self, prompt: str, timeout: int = 30) -> tuple[Optional[str], Optional[LLMErrorContext]]:
        """
        Generate text from prompt
        
        Returns: (response, error_context)
        - If successful: (response_text, None)
        - If failed: (None, LLMErrorContext)
        """
        pass

    @staticmethod
    def _classify_error(exception: Exception) -> LLMErrorType:
        """오류 타입 분류"""
        exc_name = type(exception).__name__
        exc_str = str(exception).lower()

        # 타임아웃 오류
        if "timeout" in exc_name.lower() or "timeout" in exc_str:
            return LLMErrorType.TIMEOUT_ERROR

        # 네트워크 오류
        if any(x in exc_name.lower() for x in ["connection", "dns", "network", "refused"]):
            return LLMErrorType.NETWORK_ERROR
        if any(x in exc_str for x in ["connection refused", "name or service not known", "getaddrinfo failed"]):
            return LLMErrorType.NETWORK_ERROR

        # 파싱 오류
        if any(x in exc_name.lower() for x in ["json", "decode", "parse"]):
            return LLMErrorType.PARSE_ERROR
        if any(x in exc_str for x in ["json decode", "json parse", "decode error", "parse error"]):
            return LLMErrorType.PARSE_ERROR

        # HTTP 5xx (모델 오류)
        if "5" in exc_str or "500" in exc_str:
            return LLMErrorType.MODEL_ERROR

        return LLMErrorType.UNKNOWN_ERROR


class OllamaClient(LLMClient):
    """Ollama local LLM client with retry and error classification"""

    def __init__(self, endpoint: str, model: str, max_retries: int = 3):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.max_retries = max_retries
        self._failure_count = 0
        self._circuit_open_until = 0.0
        self._last_skip_log_at = 0.0
        if httpx:
            self.client = httpx.AsyncClient(timeout=None)  # per-request timeout 사용
        else:
            self.client = None
        logger.info(f"OllamaClient initialized: {endpoint}, model={model}, max_retries={max_retries}")

    async def generate(self, prompt: str, timeout: int = 30) -> tuple[Optional[str], Optional[LLMErrorContext]]:
        """Generate text using Ollama with retry logic"""
        if self.client is None or httpx is None:
            error_ctx = LLMErrorContext(
                error_type=LLMErrorType.UNKNOWN_ERROR,
                message="LLM unavailable: httpx not installed",
                recovery_strategy="skip",
            )
            return None, error_ctx

        # Check circuit breaker
        now = time.monotonic()
        if now < self._circuit_open_until:
            if now - self._last_skip_log_at >= 30:
                remaining = self._circuit_open_until - now
                logger.warning(
                    f"OllamaClient circuit breaker open for {remaining:.1f}s (failures: {self._failure_count})"
                )
                self._last_skip_log_at = now
            
            error_ctx = LLMErrorContext(
                error_type=LLMErrorType.CIRCUIT_BREAKER_OPEN,
                message=f"Circuit breaker open for {self._circuit_open_until - now:.1f}s",
                recovery_strategy="skip",
            )
            return None, error_ctx

        # Retry loop
        last_exception = None
        for attempt in range(1, self.max_retries + 1):
            start_time = time.monotonic()
            try:
                if _LLM_DEBUG:
                    print(f"\n{'='*60}\n[LLM PROMPT → {self.model}]\n{'='*60}\n{prompt}\n{'='*60}", flush=True)
                response = await self.client.post(
                    f"{self.endpoint}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                    },
                    timeout=timeout,
                )
                response.raise_for_status()
                data = response.json()

                # Response validation
                if "response" not in data:
                    error_ctx = LLMErrorContext(
                        error_type=LLMErrorType.VALIDATION_ERROR,
                        message=f"Missing 'response' field in Ollama response: {list(data.keys())}",
                        attempt_number=attempt,
                        max_attempts=self.max_retries,
                        recovery_strategy="fallback",
                        elapsed_ms=int((time.monotonic() - start_time) * 1000),
                    )
                    logger.warning(f"OllamaClient validation error: {error_ctx.message}")
                    if error_ctx.is_retryable():
                        await asyncio.sleep(0.5 * (2 ** (attempt - 1)))  # Exponential backoff
                        continue
                    return None, error_ctx

                # Success!
                self._failure_count = 0
                self._circuit_open_until = 0.0
                elapsed_ms = int((time.monotonic() - start_time) * 1000)
                raw_response = data.get("response", "")
                if _LLM_DEBUG:
                    print(f"\n{'='*60}\n[LLM RESPONSE ← {self.model}] ({elapsed_ms}ms)\n{'='*60}\n{raw_response}\n{'='*60}", flush=True)
                logger.info(f"OllamaClient generated response in {elapsed_ms}ms (attempt {attempt}/{self.max_retries})")
                return raw_response, None

            except Exception as e:
                elapsed_ms = int((time.monotonic() - start_time) * 1000)
                error_type = LLMClient._classify_error(e)
                last_exception = e
                
                # Log retry attempt
                is_retryable = attempt < self.max_retries
                log_level = "warning" if is_retryable else "error"
                getattr(logger, log_level)(
                    f"OllamaClient attempt {attempt}/{self.max_retries} failed "
                    f"({error_type.value}, {elapsed_ms}ms): {type(e).__name__}: {str(e)[:100]}"
                )

                # Exponential backoff
                if is_retryable:
                    backoff = 0.5 * (2 ** (attempt - 1))
                    logger.info(f"OllamaClient retrying after {backoff:.1f}s...")
                    await asyncio.sleep(backoff)
                    continue

        # All retries exhausted
        self._failure_count += 1
        cooldown = min(120, 5 * (2 ** min(self._failure_count - 1, 4)))
        self._circuit_open_until = time.monotonic() + cooldown
        logger.error(
            f"OllamaClient exhausted {self.max_retries} retries, "
            f"circuit open for {cooldown}s (total failures: {self._failure_count})"
        )

        error_type = LLMClient._classify_error(last_exception) if last_exception else LLMErrorType.UNKNOWN_ERROR
        error_ctx = LLMErrorContext(
            error_type=error_type,
            message=str(last_exception) if last_exception else "Unknown error after retries",
            original_exception=last_exception,
            attempt_number=self.max_retries,
            max_attempts=self.max_retries,
            recovery_strategy="fallback",
            elapsed_ms=int((time.monotonic() - start_time) * 1000) if last_exception else 0,
        )
        return None, error_ctx


class FallbackClient(LLMClient):
    """Fallback client when LLM unavailable"""

    async def generate(self, prompt: str, timeout: int = 30) -> tuple[Optional[str], Optional[LLMErrorContext]]:
        """Return fallback response"""
        error_ctx = LLMErrorContext(
            error_type=LLMErrorType.UNKNOWN_ERROR,
            message="LLM unavailable - using fallback",
            recovery_strategy="fallback",
        )
        return None, error_ctx


def _ensure_ollama_available(endpoint: str, timeout_seconds: float = 3.0) -> None:
    url = f"{endpoint.rstrip('/')}/api/version"
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            if getattr(response, "status", 200) != 200:
                raise RuntimeError(f"Ollama returned HTTP {getattr(response, 'status', 'unknown')}")
    except Exception as exc:
        raise RuntimeError(f"Ollama is not available at {endpoint}") from exc


def make_llm_client(config: dict[str, Any]) -> LLMClient:
    """Factory function to create LLM client"""
    provider = config.get("provider", "ollama").lower()

    if provider == "ollama":
        endpoint = config.get("endpoint", "http://localhost:11434")
        model = config.get("model", "gemma4:e2b")
        max_retries = config.get("max_retries", 3)
        _ensure_ollama_available(endpoint)
        return OllamaClient(endpoint=endpoint, model=model, max_retries=max_retries)

    raise RuntimeError(f"Unsupported LLM provider: {provider}")
