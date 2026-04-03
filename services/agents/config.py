from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    redis_url: str = "redis://localhost:6379"
    core_api_url: str = "http://localhost:8000"
    log_level: str = "info"

    # ── LLM 백엔드 선택 ──────────────────────────────────────────────────────
    # "claude"  : Anthropic API 사용 (기본값)
    # "ollama"  : 로컬 Ollama 서버 사용 (Apple Silicon Metal 백엔드)
    # "vllm"    : vLLM 서버 사용 (NVIDIA GPU / Apple Silicon MPS)
    llm_backend: Literal["claude", "ollama", "vllm"] = "claude"

    # Claude 설정 (llm_backend="claude" 일 때 사용)
    anthropic_api_key: str = ""
    claude_model: str = "claude-haiku-4-5-20251001"

    # Ollama 설정 (llm_backend="ollama" 일 때 사용)
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b"
    ollama_think: bool = False   # True: 사고 모드 활성화 / False: 빠른 응답

    # vLLM 설정 (llm_backend="vllm" 일 때 사용)
    vllm_url: str = "http://localhost:8000"
    vllm_model: str = "Qwen/Qwen2.5-3B-Instruct"


settings = Settings()
