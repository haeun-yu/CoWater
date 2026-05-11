"""
LLM 명령 시나리오 스모크 테스트

이 시나리오는 System Agent의 사용자 명령 해석 경로가 실제로 Ollama를 통해
작동하는지 확인한다.

실행 전 필수:
  server/registration/  (port 8280)
  server/system-agent/   (port 9116)

실행:
  python3 docs/run_llm_command_scenario.py
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any


SYSTEM_AGENT = "http://127.0.0.1:9116"
REGISTRY = "http://127.0.0.1:8280"


def http(method: str, url: str, body: dict | None = None, timeout: int = 10) -> Any:
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = response.read()
            return json.loads(payload) if payload else {}
    except urllib.error.HTTPError as exc:
        try:
            return json.loads(exc.read())
        except Exception:
            return {"error": exc.code, "reason": exc.reason}
    except Exception as exc:
        return {"error": str(exc)}


def section(title: str) -> None:
    print(f"\n{'=' * 55}")
    print(f"  {title}")
    print(f"{'=' * 55}")


def check(label: str, cond: bool, detail: str = "") -> bool:
    mark = "✅" if cond else "❌"
    print(f"  {mark} {label}" + (f" — {detail}" if detail else ""))
    return cond


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def wait_for_token(timeout_seconds: int = 30) -> tuple[dict[str, Any], str]:
    deadline = time.time() + timeout_seconds
    state: dict[str, Any] = {}
    while time.time() < deadline:
        state = as_dict(http("GET", f"{SYSTEM_AGENT}/state"))
        token = str(state.get("token") or "")
        if token:
            return state, token
        time.sleep(1)
    return state, ""


def wait_for_llm_marker(timeout_seconds: int = 180, interval_seconds: int = 2) -> list[dict[str, Any]]:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        state = as_dict(http("GET", f"{SYSTEM_AGENT}/state"))
        memory = state.get("memory") or []
        markers = [
            item for item in memory
            if isinstance(item, dict) and item.get("kind") == "command_llm_interpreted"
        ]
        if markers:
            return markers
        time.sleep(interval_seconds)
    return []


def wait_for_mission_status(approval_id: str, timeout_seconds: int = 180, interval_seconds: int = 3) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    mission: dict[str, Any] = {}
    while time.time() < deadline:
        mission_list = as_list(http("GET", f"{REGISTRY}/missions"))

        mission = next(
            (
                item for item in mission_list
                if str(item.get("approval_id") or "") == approval_id
                or str(item.get("proposal_id") or "") == approval_id
            ),
            mission,
        )
        status = str(mission.get("status") or "")
        final_status = str(as_dict(mission.get("final_result")).get("status") or "")
        if status == "completed" or final_status == "completed" or status == "failed":
            return mission
        time.sleep(interval_seconds)
    return mission


def wait_for_command_result(request_id: str, timeout_seconds: int = 240, interval_seconds: int = 2) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    latest: dict[str, Any] = {}
    while time.time() < deadline:
        latest = as_dict(http("GET", f"{SYSTEM_AGENT}/commands/{request_id}"))
        status = str(latest.get("status") or "")
        if status in {"completed", "failed"}:
            return latest
        time.sleep(interval_seconds)
    return latest


def print_mission_execution_results(mission: dict[str, Any]) -> None:
    results = as_list(mission.get("device_execution_results"))
    print(f"  • device_execution_results: {len(results)}개")
    for item in results[:5]:
        print(
            "  • result: "
            f"{item.get('status') or item.get('task_status') or 'unknown'} "
            f"| device={item.get('device_id') or item.get('source_device_id') or ''} "
            f"| action={item.get('device_agent_judgement') or item.get('action') or ''} "
            f"| summary={item.get('data_summary') or item.get('failure_reason') or item.get('failure_message') or ''}"
        )


section("Step 0. System Agent 상태 확인")
health = as_dict(http("GET", f"{SYSTEM_AGENT}/health"))
check("System Agent 준비됨", health.get("status") == "ok", health.get("agent_id", "") or str(health))

state, token = wait_for_token()
check("System Agent 토큰 확보", bool(token), token[:16])

if not token:
    print("\n⛔ System Agent token을 확보하지 못했습니다.")
    raise SystemExit(1)

command_endpoint = f"{SYSTEM_AGENT}/agents/{token}/command?async_mode=true"
section("Step 1. LLM 명령 전송")
command = {
    "action": "37.005, 129.425 좌표의 해역에서 기뢰를 탐지하고 제거해줘",
    "reason": "사용자 직접 명령 경로 검증",
    "goal": "기뢰 탐지 및 제거",
    "priority": "high",
    "params": {
        "location": {"latitude": 37.005, "longitude": 129.425},
        "desired_outcome": "mine_clearance",
    },
}
response = as_dict(http("POST", command_endpoint, command, timeout=180))
check("명령 엔드포인트 응답 수신", bool(response), json.dumps(response, ensure_ascii=False)[:120])

request_id = str(response.get("request_id") or "")
check("명령 비동기 접수", response.get("accepted") is True and bool(request_id), request_id)

result_payload: dict[str, Any] = {}
result_command: dict[str, Any] = {}
if request_id:
    command_status = wait_for_command_result(request_id)
    check("비동기 명령 완료", str(command_status.get("status") or "") == "completed", str(command_status.get("status") or "unknown"))
    result_payload = as_dict(command_status.get("result"))
    result_command = as_dict(result_payload.get("command") or result_payload.get("resolved_command"))
    check("응답이 전달됨", result_payload.get("delivered") is True, "")
    check("LLM 재해석 반영", result_command.get("action") in {"mission.assign", "task.assign", "route_direct", "route_via_middle"}, str(result_command.get("action")))
    check("명령 재해석이 mission.assign으로 수렴", result_command.get("action") == "mission.assign", str(result_command.get("action")))
else:
    check("비동기 명령 완료", False, "request_id missing")
    check("응답이 전달됨", False, "")
    check("LLM 재해석 반영", False, "None")
    check("명령 재해석이 mission.assign으로 수렴", False, "None")

mission_bundle = as_dict(result_payload.get("mission_bundle"))
proposal = as_dict(mission_bundle.get("proposal"))
approval = as_dict(mission_bundle.get("approval"))
if proposal:
    print(f"  • proposal_id: {proposal.get('proposal_id')}")
if approval:
    print(f"  • approval_id: {approval.get('approval_id')}")

section("Step 2. 상태에 LLM 해석 흔적 확인")
llm_markers = wait_for_llm_marker()
check("command_llm_interpreted 기록", bool(llm_markers), f"{len(llm_markers)}개")

if llm_markers:
    latest = llm_markers[-1]
    llm = as_dict(latest.get("llm"))
    print(f"  • reasoning: {str(llm.get('reasoning') or '')[:120]}")
    print(f"  • action: {llm.get('action') or result_command.get('action')}")

if approval.get("approval_id"):
    section("Step 3. 승인 후 미션 확인")
    approval_id = str(approval.get("approval_id"))
    decision = as_dict(http(
        "POST",
        f"{SYSTEM_AGENT}/approvals/{approval_id}/decision",
        {
            "approved": True,
            "decided_by": "demo_operator",
            "notes": "LLM command demo auto-approval",
        },
    ))
    check("승인 응답", bool(decision), json.dumps(decision, ensure_ascii=False)[:120])
    mission = wait_for_mission_status(approval_id)
    status = mission.get("status", "미정")
    final_status = as_dict(mission.get("final_result")).get("status") or ""
    effective_complete = status == "completed" or final_status == "completed"
    check("미션 기록 확인", bool(mission) and effective_complete, f"{status} (final_result={final_status})")
    if mission:
        print(f"  • mission_id: {mission.get('mission_id')}")
        print(f"  • status: {status}")
        print(f"  • title: {mission.get('title')}")
        steps = as_list(mission.get("steps"))
        if steps:
            print(f"  • steps ({len(steps)}개):")
            for s in steps:
                print(f"    - step_id={s.get('step_id')} type={s.get('step_type')} status={s.get('status')}")
                for t in as_list(s.get("tasks")):
                    print(f"      task={t.get('task_id')} action={t.get('action')} device={t.get('target_device_id')} exec={t.get('execution_status')}")
        print_mission_execution_results(mission)
        final_result = mission.get("final_result") or {}
        if final_result:
            print(f"  • final_result.status: {final_result.get('status')}")
            if final_result.get("summary") or final_result.get("reason"):
                print(f"  • final_result.detail: {final_result.get('summary') or final_result.get('reason')}")
        if status == "running":
            print("  ⚠️  미션이 아직 실행 중입니다 (180초 제한 도달). 디바이스 응답 대기 중이거나 서비스 재시작이 필요할 수 있습니다.")

section("완료")
print("  ✅ System Agent LLM 명령 경로 확인 완료")
