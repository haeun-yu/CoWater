"""Analysis 서비스 설정"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Analysis 서비스 환경 변수"""

    # 기본
    redis_url: str = "redis://localhost:6379"
    core_api_url: str = "http://localhost:8000"
    log_level: str = "info"

    # Ollama (호스트 시스템의 로컬 LLM)
    # Mac/Windows Docker Desktop: http://host.docker.internal:11434
    # Linux (호스트 직접 실행): http://localhost:11434
    ollama_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "qwen2.5:3b"

    # Heartbeat
    heartbeat_interval_sec: int = 60

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
