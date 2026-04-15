"""Response 서비스 설정"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Response 서비스 환경 변수"""

    # 기본
    redis_url: str = "redis://localhost:6379"
    core_api_url: str = "http://localhost:8000"
    log_level: str = "info"

    llm_backend: str = "ollama"
    anthropic_api_key: str = ""
    claude_model: str = "claude-haiku-4-5-20251001"
    ollama_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "qwen2.5:3b"
    ollama_think: bool = False
    vllm_url: str = "http://localhost:8000"
    vllm_model: str = "Qwen/Qwen2.5-3B-Instruct"
    distress_agent_max_tokens: int = 600
    claude_timeout_sec: float = 60.0
    claude_max_attempts: int = 3
    claude_base_delay_sec: float = 1.0
    local_llm_timeout_sec: float = 120.0
    local_llm_max_attempts: int = 2
    local_llm_base_delay_sec: float = 2.0
    distress_alert_cooldown_sec: int = 300

    # Heartbeat
    heartbeat_interval_sec: int = 60

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
