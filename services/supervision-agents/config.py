"""Supervision 서비스 설정"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Supervision 서비스 환경 변수"""

    # 기본
    redis_url: str = "redis://localhost:6379"
    log_level: str = "info"

    # 모니터링
    health_check_interval_sec: int = 60

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
