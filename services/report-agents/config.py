"""Report 서비스 설정"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Report 서비스 환경 변수

    ⚠️ DATABASE_URL 불필요 — Core API를 통해 리포트 저장 (Core만 DB 접근)
    """

    # 기본
    redis_url: str = "redis://localhost:6379"
    core_api_url: str = "http://localhost:8000"
    log_level: str = "info"

    # LLM (보고서 생성)
    llm_backend: str = "ollama"  # "claude" | "ollama" | "vllm"
    anthropic_api_key: str = ""
    claude_model: str = "claude-haiku-4-5-20251001"
    ollama_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "gemma4:e2b"
    vllm_url: str = "http://vllm:8000"
    vllm_model: str = "Qwen/Qwen2.5-3B-Instruct"
    ollama_think: bool = False

    # LLM Timeout
    claude_timeout_sec: int = 60
    local_llm_timeout_sec: int = 60
    claude_max_attempts: int = 3
    local_llm_max_attempts: int = 3
    claude_base_delay_sec: float = 1.0
    local_llm_base_delay_sec: float = 1.0
    report_alert_max_tokens: int = 1024
    report_incident_max_tokens: int = 2048

    # Heartbeat
    heartbeat_interval_sec: int = 60

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
