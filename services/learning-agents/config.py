"""Learning 서비스 설정"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Learning 서비스 환경 변수"""

    # 기본
    redis_url: str = "redis://localhost:6379"
    core_api_url: str = "http://localhost:8000"
    log_level: str = "info"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
