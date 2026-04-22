#!/usr/bin/env python3
"""
A2A Detection Agent Server

Google A2A (Agent-to-Agent) 2025년 4월 표준을 구현합니다.

엔드포인트:
- GET  /.well-known/agent.json    → Agent Card (capability 선언)
- POST /tasks/send                 → Task 수신 및 실행
- GET  /tasks/{task_id}            → Task 상태 및 결과 조회

Learning Agent가 Detection Agent에게 rule update를 제안하는
Task를 전송하고, Detection Agent가 이를 처리합니다.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

# ─────────────────────────────────────────────────────────────────────────────
# 로깅
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [A2A Detection Agent] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# A2A Agent Card (Google A2A 표준)
# ─────────────────────────────────────────────────────────────────────────────

AGENT_CARD = {
    "name": "cowater-detection-agent",
    "displayName": "CoWater Detection Agent",
    "description": (
        "연안 VTS Detection Agent. "
        "CPA/Anomaly/Zone/Distress/Mine rule 기반 감지 및 임계값 조정을 처리합니다. "
        "Learning Agent의 rule update 제안을 수신하고 신뢰도에 따라 "
        "즉시 적용 또는 보류 처리합니다."
    ),
    "url": "http://detection-agent:8001",
    "version": "1.0.0",
    "apiVersion": "a2a-2025-04",
    "capabilities": {
        "streaming": False,
        "pushNotifications": False,
        "rateLimit": None,
    },
    "skills": [
        {
            "id": "suggest_rule_update",
            "name": "Suggest Rule Update",
            "description": (
                "Learning Agent의 rule update 제안을 수신하고 처리합니다. "
                "confidence >= 0.6이면 즉시 적용, 미만이면 pending으로 보류합니다."
            ),
            "inputModes": ["data"],
            "outputModes": ["data"],
            "examples": [
                "CPA critical_cpa_nm을 0.5 → 1.0으로 조정 (confidence 0.72)",
                "Anomaly rot_threshold를 20 → 30으로 조정 (confidence 0.45) → pending",
            ],
        }
    ],
    "defaultInputMode": "data",
    "defaultOutputMode": "data",
}

# ─────────────────────────────────────────────────────────────────────────────
# Mock 설정 데이터 (프로젝트 config 반영)
# ─────────────────────────────────────────────────────────────────────────────

_current_config = {
    "detection-cpa": {
        "critical_cpa_nm": 0.5,
        "warning_cpa_nm": 2.0,
        "critical_tcpa_min": 10.0,
        "warning_tcpa_min": 20.0,
    },
    "detection-anomaly": {
        "ais_timeout_sec": 90,
        "rot_threshold": 20.0,
        "heading_threshold": 45.0,
        "speed_drop_threshold": 5.0,
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# A2A Task 저장소 (인메모리, POC용)
# ─────────────────────────────────────────────────────────────────────────────

_tasks: dict[str, dict] = {}

# ─────────────────────────────────────────────────────────────────────────────
# Pydantic 모델 (A2A Task 스펙)
# ─────────────────────────────────────────────────────────────────────────────


class MessagePart(BaseModel):
    """A2A message part"""

    type: str  # "text" | "data"
    text: Optional[str] = None
    data: Optional[dict] = None


class Message(BaseModel):
    """A2A message"""

    role: str  # "user" | "assistant"
    parts: list[MessagePart]


class TaskSendRequest(BaseModel):
    """A2A Task send request"""

    id: Optional[str] = None  # client가 지정하거나 서버가 생성
    skill_id: str
    message: Message


class TaskStatus(BaseModel):
    """A2A Task status"""

    state: str  # "submitted" | "working" | "completed" | "failed"


class TaskArtifact(BaseModel):
    """A2A artifact (결과 데이터 컨테이너)"""

    name: str
    parts: list[MessagePart]


class TaskResponse(BaseModel):
    """A2A Task response"""

    id: str
    status: TaskStatus
    artifacts: list[TaskArtifact] = []


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI app
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="CoWater Detection Agent (A2A)",
    description="Google A2A 표준 구현",
    version="1.0.0",
)


# ─────────────────────────────────────────────────────────────────────────────
# A2A 엔드포인트
# ─────────────────────────────────────────────────────────────────────────────


@app.get("/.well-known/agent.json")
async def get_agent_card():
    """
    A2A Agent Card 반환

    클라이언트가 이 엔드포인트로 에이전트의 capability를 discovery합니다.
    """
    logger.info("Agent Card requested")
    return AGENT_CARD


@app.post("/tasks/send", response_model=TaskResponse)
async def send_task(req: TaskSendRequest):
    """
    A2A Task 수신 및 동기 실행

    Learning Agent가 rule update 제안을 전송합니다.

    Request body:
    {
      "skill_id": "suggest_rule_update",
      "message": {
        "role": "user",
        "parts": [{
          "type": "data",
          "data": {
            "target_agent_id": "detection-cpa",
            "old_config": {"critical_cpa_nm": 0.5},
            "new_config": {"critical_cpa_nm": 1.0},
            "reason": "FP rate 35% — CPA threshold 상향",
            "confidence": 0.72,
            ...
          }
        }]
      }
    }

    Response body (A2A Task):
    {
      "id": "uuid",
      "status": {"state": "completed"},
      "artifacts": [{
        "name": "rule_update_result",
        "parts": [{
          "type": "data",
          "data": {
            "target_agent_id": "detection-cpa",
            "applied_changes": {...},
            "pending_changes": {...},
            "current_config": {...}
          }
        }]
      }]
    }
    """
    task_id = req.id or str(uuid4())

    logger.info(f"Task received: {task_id} (skill: {req.skill_id})")

    # Task 저장소 초기화
    _tasks[task_id] = {
        "id": task_id,
        "status": {"state": "working"},
        "artifacts": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # ─────────────────────────────────────────────────────────────────────────
    # Task 처리 로직
    # ─────────────────────────────────────────────────────────────────────────

    try:
        # Skill 검증
        if req.skill_id != "suggest_rule_update":
            raise ValueError(f"Unknown skill: {req.skill_id}")

        # Message 파싱
        data_part = next(
            (p.data for p in req.message.parts if p.type == "data"), None
        )
        if not data_part:
            raise ValueError("No data part in message")

        logger.debug(f"Task payload: {json.dumps(data_part, indent=2)}")

        # 필수 필드 검증
        target_agent = data_part.get("target_agent_id")
        new_config = data_part.get("new_config", {})
        old_config = data_part.get("old_config", {})
        reason = data_part.get("reason", "")
        confidence = data_part.get("confidence", 0.5)

        if not target_agent:
            raise ValueError("target_agent_id is required")

        if target_agent not in _current_config:
            raise ValueError(f"Unknown target agent: {target_agent}")

        logger.info(
            f"Processing rule update for {target_agent} "
            f"(confidence: {confidence:.2f}, reason: {reason})"
        )

        # 임계값 조정 로직
        applied = {}
        pending = {}

        for param, new_val in new_config.items():
            if param not in _current_config[target_agent]:
                logger.warning(f"Unknown parameter: {target_agent}.{param}")
                continue

            old_val = _current_config[target_agent][param]

            if confidence >= 0.6:
                # 신뢰도 충분 → 즉시 적용
                _current_config[target_agent][param] = new_val
                applied[param] = {
                    "from": old_val,
                    "to": new_val,
                    "confidence": confidence,
                }
                logger.info(
                    f"  ✓ Applied: {target_agent}.{param} = {new_val} "
                    f"(was {old_val})"
                )
            else:
                # 신뢰도 부족 → 보류
                pending[param] = {
                    "proposed": new_val,
                    "current": old_val,
                    "confidence": confidence,
                    "reason": "confidence < 0.6",
                }
                logger.info(
                    f"  ⏸ Pending: {target_agent}.{param} = {new_val} "
                    f"(confidence {confidence:.2f} < 0.6)"
                )

        # Task 결과 생성
        result_data = {
            "target_agent_id": target_agent,
            "applied_changes": applied,
            "pending_changes": pending,
            "current_config": _current_config[target_agent],
            "reason": reason,
            "confidence": confidence,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }

        # Task 상태 업데이트
        _tasks[task_id]["status"] = {"state": "completed"}
        _tasks[task_id]["artifacts"] = [
            {
                "name": "rule_update_result",
                "parts": [{"type": "data", "data": result_data}],
            }
        ]

        logger.info(
            f"Task {task_id} completed: "
            f"{len(applied)} applied, {len(pending)} pending"
        )

    except Exception as e:
        logger.error(f"Task {task_id} failed: {str(e)}")

        _tasks[task_id]["status"] = {"state": "failed"}
        _tasks[task_id]["artifacts"] = [
            {
                "name": "error",
                "parts": [{"type": "data", "data": {"error": str(e)}}],
            }
        ]

    return TaskResponse(**_tasks[task_id])


@app.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str):
    """
    Task 상태 및 결과 조회

    클라이언트가 작업 완료 여부를 폴링하거나 최종 결과를 확인합니다.
    """
    if task_id not in _tasks:
        logger.warning(f"Task not found: {task_id}")
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    logger.info(f"Task status requested: {task_id}")
    return TaskResponse(**_tasks[task_id])


# ─────────────────────────────────────────────────────────────────────────────
# Health Check
# ─────────────────────────────────────────────────────────────────────────────


@app.get("/health")
async def health():
    """Service 헬스 체크"""
    return {
        "status": "healthy",
        "agent": AGENT_CARD["name"],
        "tasks_count": len(_tasks),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("=" * 70)
    logger.info("CoWater Detection Agent (A2A) — Google A2A 2025-04 Standard")
    logger.info("=" * 70)
    logger.info("")
    logger.info("Endpoints:")
    logger.info("  GET  /.well-known/agent.json → Agent Card")
    logger.info("  POST /tasks/send            → Task 수신 및 실행")
    logger.info("  GET  /tasks/{task_id}       → Task 조회")
    logger.info("  GET  /health                → Health check")
    logger.info("")
    logger.info("Starting server on 0.0.0.0:8001...")
    logger.info("=" * 70)

    uvicorn.run(app, host="0.0.0.0", port=8001)
