"""
Shared LLM Client - supports Ollama and other LLM providers
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

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
        if httpx:
            self.client = httpx.AsyncClient(timeout=timeout if (timeout := 60) else 60)
        else:
            self.client = None
        logger.info(f"OllamaClient initialized: {endpoint}, model={model}")

    async def generate(self, prompt: str, timeout: int = 30) -> str:
        """Generate text using Ollama"""
        if self.client is None or httpx is None:
            return "LLM unavailable: httpx not installed"

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
            return data.get("response", "")
        except Exception as e:
            logger.error(f"Ollama generation failed: {e}")
            return f"LLM error: {str(e)}"


class FallbackClient(LLMClient):
    """Fallback client when LLM unavailable"""

    async def generate(self, prompt: str, timeout: int = 30) -> str:
        """Return empty response"""
        return "LLM unavailable - using fallback"


def make_llm_client(config: dict[str, Any]) -> LLMClient:
    """Factory function to create LLM client"""
    if not config.get("enabled", False):
        logger.info("LLM disabled in config")
        return FallbackClient()

    provider = config.get("provider", "ollama").lower()

    if provider == "ollama":
        endpoint = config.get("endpoint", "http://localhost:11434")
        model = config.get("model", "gemma4:e2b")
        try:
            return OllamaClient(endpoint=endpoint, model=model)
        except Exception as e:
            logger.error(f"Failed to create OllamaClient: {e}")
            return FallbackClient()

    logger.warning(f"Unknown provider: {provider}")
    return FallbackClient()
