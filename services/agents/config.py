from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    redis_url: str = "redis://localhost:6379"
    core_api_url: str = "http://localhost:8000"
    anthropic_api_key: str = ""
    log_level: str = "info"

    claude_model: str = "claude-sonnet-4-6"


settings = Settings()
