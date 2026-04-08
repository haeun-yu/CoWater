from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    moth_server_url: str = "wss://cobot.center:8287"
    redis_url: str = "redis://localhost:6379"
    channels_config: str = "config.yaml"
    log_level: str = "info"
    raw_payload_mode: Literal["off", "cache", "db"] = "cache"
    raw_payload_protocols: str = "ais,ros,mavlink,nmea"
    raw_payload_max_bytes: int = 4096
    raw_payload_ttl_sec: int = 86400

    # Moth 재연결 설정
    reconnect_delay_s: float = 5.0
    reconnect_max_attempts: int = 0  # 0 = 무제한


settings = Settings()
