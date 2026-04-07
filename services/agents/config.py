from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    redis_url: str = "redis://localhost:6379"
    core_api_url: str = "http://localhost:8000"
    log_level: str = "info"

    # ── LLM 백엔드 선택 ──────────────────────────────────────────────────────
    # "claude"  : Anthropic API 사용 (기본값)
    # "ollama"  : 로컬 Ollama 서버 사용 (Apple Silicon Metal 백엔드)
    # "vllm"    : vLLM 서버 사용 (NVIDIA GPU / Apple Silicon MPS)
    llm_backend: Literal["claude", "ollama", "vllm"] = "claude"

    # Claude 설정 (llm_backend="claude" 일 때 사용)
    anthropic_api_key: str = ""
    claude_model: str = "claude-haiku-4-5-20251001"

    # Ollama 설정 (llm_backend="ollama" 일 때 사용)
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b"
    ollama_think: bool = False   # True: 사고 모드 활성화 / False: 빠른 응답
    # 챗봇 전용 모델 (비어있으면 ollama_model / claude_model 과 동일)
    # 예: CHAT_OLLAMA_MODEL=qwen2.5:0.5b 로 챗봇만 경량 모델 사용
    chat_ollama_model: str = ""
    chat_claude_model: str = ""

    # vLLM 설정 (llm_backend="vllm" 일 때 사용)
    vllm_url: str = "http://localhost:8000"
    vllm_model: str = "Qwen/Qwen2.5-3B-Instruct"

    # AI 호출 게이팅
    # 동일 대상(alert_type+platform)에 대한 AI 재호출 쿨다운(초)
    ai_alert_cooldown_sec: int = 120
    # AI 분석 최소 심각도 ("warning" 또는 "critical")
    ai_min_severity: Literal["warning", "critical"] = "warning"

    # ── AI 에이전트 토큰 제한 ─────────────────────────────────────────────────
    anomaly_ai_max_tokens: int = 512
    distress_agent_max_tokens: int = 600
    report_alert_max_tokens: int = 1024
    report_incident_max_tokens: int = 2048
    chat_agent_max_tokens: int = 1024  # 챗봇 응답 최대 토큰

    # ── LLM 타임아웃 / 재시도 ────────────────────────────────────────────────
    # Claude API
    claude_timeout_sec: float = 60.0
    claude_max_attempts: int = 3
    claude_base_delay_sec: float = 1.0
    # 로컬 LLM (Ollama / vLLM) — 추론이 느릴 수 있어 더 길게 설정
    local_llm_timeout_sec: float = 120.0
    local_llm_max_attempts: int = 2
    local_llm_base_delay_sec: float = 2.0

    # ── Rule 에이전트 임계값 ──────────────────────────────────────────────────
    # AnomalyRuleAgent
    ais_timeout_sec: int = 90           # 이 시간(초) 이상 AIS 미수신 → 소실 경보
    speed_drop_threshold: float = 5.0   # knots — 한 틱에 이 이상 감소 시 경보
    rot_threshold: float = 25.0         # degrees/min — 이 이상 선회 시 경보
    # CPAAgent 기본 임계값 (PATCH /agents/cpa-agent/config 로도 런타임 변경 가능)
    cpa_warning_nm: float = 0.5         # Warning CPA 거리 (해리)
    cpa_warning_tcpa_min: float = 30.0  # Warning TCPA (분)
    cpa_critical_nm: float = 0.2        # Critical CPA 거리 (해리)
    cpa_critical_tcpa_min: float = 10.0 # Critical TCPA (분)

    # ── 런타임 타이밍 ─────────────────────────────────────────────────────────
    ai_task_timeout_sec: float = 120.0     # AI 에이전트 단일 호출 최대 시간 (초)
    reconnect_max_delay_sec: float = 60.0  # 컨슈머 재연결 최대 대기 (초)
    shutdown_drain_timeout_sec: float = 15.0  # 종료 시 AI 태스크 drain 대기 (초)
    ais_check_interval_sec: int = 20       # AIS 타임아웃 체크 주기 (초)
    zone_reload_interval_sec: int = 300    # Zone 재로드 주기 (초)


settings = Settings()
