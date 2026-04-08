"""
Chat Agent — 운항자와 직접 소통하는 AI 보좌관.

현재 해양 상황(관제 선박 상태, 활성 경보)을 실시간 컨텍스트로 포함하여
운항 상황 요약, 위험 분석, 대처 방법 등을 한국어로 답변한다.

다른 에이전트와 달리 이 에이전트는:
- on_platform_report / on_alert 로 최신 상황을 캐싱 (컨텍스트용)
- 경보는 직접 발행하지 않음
- /chat REST 엔드포인트를 통해 운항자와 1:1 대화
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import redis.asyncio as aioredis

from ai.llm_client import make_llm_client
from base import Agent, PlatformReport
from config import settings

logger = logging.getLogger(__name__)


def _make_chat_llm_client():
    """채팅 전용 LLM 클라이언트 생성.

    CHAT_OLLAMA_MODEL / CHAT_CLAUDE_MODEL 환경변수가 설정되어 있으면
    해당 모델을 사용하고, 없으면 기본 에이전트 모델과 동일하다.
    """
    from copy import copy
    import pydantic_settings

    # 채팅 전용 모델이 설정되지 않았으면 기본 클라이언트 사용
    backend = settings.llm_backend.lower()
    if backend == "ollama" and settings.chat_ollama_model:
        # 채팅 전용 Ollama 모델로 오버라이드
        from ai.llm_client import OllamaClient
        model = settings.chat_ollama_model
        logger.info("Chat agent using dedicated Ollama model: %s", model)
        return OllamaClient(
            base_url=settings.ollama_url,
            model=model,
            think=False,  # 채팅은 항상 빠른 모드
            timeout=settings.local_llm_timeout_sec,
            max_attempts=settings.local_llm_max_attempts,
            base_delay=settings.local_llm_base_delay_sec,
        )
    if backend == "claude" and settings.chat_claude_model:
        from ai.llm_client import ClaudeClient
        model = settings.chat_claude_model
        logger.info("Chat agent using dedicated Claude model: %s", model)
        return ClaudeClient(
            api_key=settings.anthropic_api_key,
            model=model,
            timeout=settings.claude_timeout_sec,
            max_attempts=settings.claude_max_attempts,
            base_delay=settings.claude_base_delay_sec,
        )
    return make_llm_client(settings)


_SYSTEM_PROMPT = """당신은 해양 통합 관제 플랫폼 CoWater의 AI 운항 보좌관입니다.

현재 시스템에서 실시간으로 수집 중인 선박 위치·경보 데이터를 기반으로
운항자(사용자)의 질문에 정확하고 실용적으로 답변하십시오.

답변 원칙:
- 제공된 현재 상황 데이터를 우선 참고하여 사실 기반 답변
- 불확실한 사항은 "확인이 필요합니다" 등으로 명시
- 긴급 상황에서는 간결하고 행동 지향적으로 (번호 목록 우선)
- 일반 질문에는 전문적이되 이해하기 쉽게
- 모든 답변은 한국어로"""


class ChatAgent(Agent):
    agent_id = "chat-agent"
    name = "AI 보좌관"
    description = "현재 해양 상황을 컨텍스트로 활용하여 운항자와 실시간 소통하는 AI 챗봇"
    agent_type = "ai"

    def __init__(self, redis: aioredis.Redis) -> None:
        super().__init__(redis)
        self._llm = _make_chat_llm_client()
        # 최신 선박 상태 캐시 (컨텍스트 구성용)
        self._recent_reports: dict[str, PlatformReport] = {}
        # 최근 경보 (최대 30건)
        self._recent_alerts: list[dict] = []

    async def on_platform_report(self, report: PlatformReport) -> None:
        """선박 위치 보고 수신 — 컨텍스트 캐시 갱신."""
        self._recent_reports[report.platform_id] = report

    async def on_alert(self, alert: dict) -> None:
        """경보 수신 — 컨텍스트 캐시 갱신 (직접 경보 발행하지 않음)."""
        if alert.get("generated_by") == self.agent_id:
            return
        self._recent_alerts = [alert, *self._recent_alerts[:29]]

    # ── 챗봇 핵심 메서드 ────────────────────────────────────────────────────────

    async def chat_stream(
        self,
        message: str,
        history: list[dict] | None = None,
        focus_platform_ids: list[str] | None = None,
    ):
        """스트리밍 응답 — 청크 단위로 텍스트를 yield한다."""
        context_block = self._build_situation_context(focus_platform_ids)
        system = _SYSTEM_PROMPT + "\n\n" + context_block
        user_prompt = _serialize_history(history or []) + message
        try:
            async for chunk in self._llm.chat_stream(
                system=system,
                user=user_prompt,
                max_tokens=settings.chat_agent_max_tokens,
            ):
                yield chunk
        except Exception:
            logger.exception("Chat agent stream failed")
            yield "[응답 실패] LLM 서버에 일시적으로 연결할 수 없습니다."

    async def chat(
        self,
        message: str,
        history: list[dict] | None = None,
        focus_platform_ids: list[str] | None = None,
    ) -> str:
        """운항자 메시지에 대한 AI 응답을 생성한다.

        Args:
            message: 사용자 입력 문자열
            history: 이전 대화 [{"role": "user"|"assistant", "content": "..."}, ...]
            focus_platform_ids: 사용자가 현재 주목 중인 선박 ID 목록 (지도 선택 등)
        """
        context_block = self._build_situation_context(focus_platform_ids)
        system = _SYSTEM_PROMPT + "\n\n" + context_block

        # 이전 대화 + 현재 메시지를 단일 user 프롬프트로 직렬화
        # (멀티턴을 지원하지 않는 LLM 백엔드 대응)
        user_prompt = _serialize_history(history or []) + message

        try:
            return await self._llm.chat(
                system=system,
                user=user_prompt,
                max_tokens=settings.chat_agent_max_tokens,
            )
        except Exception:
            logger.exception("Chat agent LLM call failed")
            return (
                "[응답 실패]\n\n"
                "LLM 서버에 일시적으로 연결할 수 없습니다. "
                "잠시 후 다시 시도하거나 관리자에게 문의하십시오."
            )

    # ── 내부 헬퍼 ───────────────────────────────────────────────────────────────

    def _build_situation_context(self, focus_platform_ids: list[str] | None) -> str:
        """현재 관제 상황을 LLM 프롬프트용 텍스트로 변환."""
        now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        lines = [f"[현재 시각] {now}", f"[관제 중인 선박] 총 {len(self._recent_reports)}척"]

        # 주목 선박 상세 정보
        if focus_platform_ids:
            focused = [
                self._recent_reports[pid]
                for pid in focus_platform_ids
                if pid in self._recent_reports
            ]
            if focused:
                lines.append("[주목 선박]")
                for r in focused:
                    lat = f"{r.lat:.4f}" if r.lat is not None else "?"
                    lon = f"{r.lon:.4f}" if r.lon is not None else "?"
                    sog = f"{r.sog}kt" if r.sog is not None else "?"
                    cog = f"{r.cog}°" if r.cog is not None else "?"
                    lines.append(
                        f"  - {r.platform_id}: 위치({lat}°N {lon}°E) "
                        f"속도={sog} 침로={cog} 상태={r.nav_status or '알 수 없음'}"
                    )

        # 전체 선박 목록 (최대 10척)
        if self._recent_reports:
            lines.append("[선박 목록 (최대 10척)]")
            for r in list(self._recent_reports.values())[:10]:
                lat = f"{r.lat:.3f}" if r.lat is not None else "?"
                lon = f"{r.lon:.3f}" if r.lon is not None else "?"
                sog = f"{r.sog}kt" if r.sog is not None else "?"
                lines.append(f"  - {r.platform_id}: ({lat}°N {lon}°E) {sog}")

        # 활성 경보
        active = [a for a in self._recent_alerts if a.get("status") == "new"]
        critical = [a for a in active if a.get("severity") == "critical"]
        warning  = [a for a in active if a.get("severity") == "warning"]

        lines.append(
            f"[활성 경보] 총 {len(active)}건 "
            f"(위험 {len(critical)}건 / 주의 {len(warning)}건)"
        )
        for a in active[:10]:
            sev   = a.get("severity", "?").upper()
            atype = a.get("alert_type", "?")
            pids  = ", ".join(a.get("platform_ids", []))
            msg   = a.get("message", "")
            lines.append(f"  - [{sev}] {atype}: {msg} ({pids})")

        return "\n".join(lines)


def _serialize_history(history: list[dict]) -> str:
    """이전 대화를 단일 텍스트 블록으로 직렬화 (최근 6턴)."""
    if not history:
        return ""
    parts: list[str] = []
    for turn in history[-6:]:
        role = "운항자" if turn.get("role") == "user" else "보좌관"
        parts.append(f"{role}: {turn.get('content', '')}")
    return "\n".join(parts) + "\n운항자: "
