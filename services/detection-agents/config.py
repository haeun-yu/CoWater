"""Detection 서비스 설정"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Detection 서비스 환경 변수"""

    # 기본
    redis_url: str = "redis://localhost:6379"
    core_api_url: str = "http://localhost:8000"
    log_level: str = "info"

    # CPA Agent 임계값
    cpa_warning_nm: float = 2.0
    cpa_warning_tcpa_min: float = 20.0
    cpa_critical_nm: float = 0.5
    cpa_critical_tcpa_min: float = 10.0

    # Anomaly Agent 임계값
    anomaly_rot_threshold: float = 20.0  # degrees/min
    anomaly_heading_threshold: float = 45.0  # degrees
    anomaly_speed_threshold: float = 5.0  # knots

    # Zone Agent
    zone_reload_interval_sec: int = 300

    # Heartbeat
    heartbeat_interval_sec: int = 60

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
