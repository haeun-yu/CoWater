from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    moth_server_url: str = "wss://cobot.center:8287"
    moth_channel_type: str = "instant"
    moth_channel_name: str = "cowater-ais"
    moth_track: str = "data"

    redis_url: str = "redis://localhost:6379/0"  # Redis pub/sub 연결
    core_api_url: str = "http://localhost:7700"  # 플랫폼 등록용
    scenario: str = "default"  # scenarios/ 디렉토리 내 파일명 (확장자 제외)
    tick_rate_hz: float = 1.0  # 시뮬레이션 틱 주기 (1Hz = 1초마다 위치 갱신)
    time_scale: float = 1.0  # 1.0 = 실시간, 2.0 = 2배속
    log_level: str = "info"


settings = Settings()
