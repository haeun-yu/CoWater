"""Analysis 서비스 설정"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Analysis 서비스 환경 변수"""

    # 기본
    redis_url: str = "redis://localhost:6379"
    core_api_url: str = "http://localhost:8000"
    log_level: str = "info"

    # Claude API
    anthropic_api_url: str = "https://api.anthropic.com/v1"
    anthropic_api_key: str = ""
    claude_model: str = "claude-haiku-4-5-20251001"

    # Heartbeat
    heartbeat_interval_sec: int = 60

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
