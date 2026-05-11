from __future__ import annotations

"""
Shared LLM Client - supports Ollama and other LLM providers
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Optional
import urllib.error
import urllib.request

try:
    import httpx
except ImportError:
    httpx = None

logger = logging.getLogger(__name__)


class LLMClient(ABC):
    """Abstract LLM Client interface"""

    @abstractmethod
    async def generate(self, prompt: str, timeout: int = 30) -> str:
        """Generate text from prompt"""
        pass


class OllamaClient(LLMClient):
    """Ollama local LLM client"""

    def __init__(self, endpoint: str, model: str):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self._failure_count = 0
        self._circuit_open_until = 0.0
        self._last_skip_log_at = 0.0
        if httpx:
            # httpx.AsyncClient의 timeout 기본값 설정 (60초)
            self.client = httpx.AsyncClient(timeout=60.0)
        else:
            self.client = None
        logger.info(f"OllamaClient initialized: {endpoint}, model={model}")

    async def generate(self, prompt: str, timeout: int = 30) -> str:
        """Generate text using Ollama"""
        if self.client is None or httpx is None:
            return "LLM unavailable: httpx not installed"

        now = time.monotonic()
        if now < self._circuit_open_until:
            if now - self._last_skip_log_at >= 30:
                logger.warning(
                    "Ollama unavailable; skipping generation for %.1fs",
                    self._circuit_open_until - now,
                )
                self._last_skip_log_at = now
            return "LLM unavailable: circuit breaker open"

        try:
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
            self._failure_count = 0
            self._circuit_open_until = 0.0
            return data.get("response", "")
        except Exception as e:
            self._failure_count += 1
            cooldown = min(120, 5 * (2 ** min(self._failure_count - 1, 4)))
            self._circuit_open_until = time.monotonic() + cooldown
            logger.warning(
                "Ollama generation failed (%s); circuit open for %ss: %s",
                type(e).__name__,
                cooldown,
                e,
            )
            return f"LLM error: {str(e)}"


class FallbackClient(LLMClient):
    """Fallback client when LLM unavailable"""

    async def generate(self, prompt: str, timeout: int = 30) -> str:
        """Return empty response"""
        return "LLM unavailable - using fallback"


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
        _ensure_ollama_available(endpoint)
        return OllamaClient(endpoint=endpoint, model=model)

    raise RuntimeError(f"Unsupported LLM provider: {provider}")
