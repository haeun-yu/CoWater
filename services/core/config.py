from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://cowater:cowater_dev@localhost:5432/cowater"
    redis_url: str = "redis://localhost:6379"
    log_level: str = "info"

    # WebSocket
    ws_ping_interval: int = 20      # seconds
    ws_ping_timeout: int = 10

    # Track 조회 기본값
    track_default_limit: int = 1000


settings = Settings()
