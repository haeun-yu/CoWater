"""
기뢰 제거 시나리오 스모크 테스트

실행 전 필수: 아래 서비스들이 모두 기동되어 있어야 함
  server/registration/  (port 8280)
  server/system-agent/  (port 9116)
  device/ --type ship --layer middle  (port 9115)
  device/ --type auv --layer lower    (port 9112)
  device/ --type rov --layer lower    (port 9113)

실행:
  python3 docs/run_mine_removal_scenario.py
"""

import json
import time
import urllib.request
import urllib.error
from datetime import datetime
from typing import Any


REGISTRY = "http://127.0.0.1:8280"
SYSTEM_AGENT = "http://127.0.0.1:9116"
AUV_PORT = 9112
ROV_PORT = 9113
SHIP_PORT = 9115


def http(method: str, url: str, body: dict | None = None) -> Any:
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"error": e.code, "reason": e.reason}
    except Exception as e:
        return {"error": str(e)}


def check(label: str, cond: bool, detail: str = "") -> bool:
    mark = "✅" if cond else "❌"
    print(f"  {mark} {label}" + (f" — {detail}" if detail else ""))
    return cond


def section(title: str) -> None:
    print(f"\n{'='*55}")
    print(f"  {title}")
    print(f"{'='*55}")


def as_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [v for v in value if isinstance(v, dict)]
    return []


def poll_latest_completion(
    alert_id: str,
    timeout_seconds: int = 60,
    interval_seconds: int = 2,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    deadline = time.time() + timeout_seconds
    latest_alert: dict[str, Any] = {}
    latest_proposal: dict[str, Any] = {}
    latest_mission: dict[str, Any] = {}

    while time.time() < deadline:
        alerts = as_list(http("GET", f"{REGISTRY}/alerts"))
        proposals = as_list(http("GET", f"{REGISTRY}/mission-proposals"))
        missions = as_list(http("GET", f"{REGISTRY}/missions"))

        latest_alert = next(
            (item for item in alerts if str(item.get("alert_id") or "") == alert_id),
            latest_alert,
        )
        latest_proposal = next(
            (item for item in proposals if str(item.get("alert_id") or "") == alert_id),
            latest_proposal,
        )
        latest_mission = next(
            (item for item in missions if str(item.get("alert_id") or "") == alert_id),
            latest_mission,
        )

        proposal_status = str(latest_proposal.get("status") or "")
        mission_status = str(latest_mission.get("status") or "")
        alert_status = str(latest_alert.get("status") or "")
        if proposal_status in {"approved", "converted", "completed"} and mission_status == "completed" and alert_status == "completed":
            break

        time.sleep(interval_seconds)

    return latest_alert, latest_proposal, latest_mission, {
        "proposal_status": proposal_status,
        "mission_status": mission_status,
        "alert_status": alert_status,
    }


# ──────────────────────────────────────────────────────────
# Step 0. 사전 점검
# ──────────────────────────────────────────────────────────
section("Step 0. 서비스 상태 점검")

ok = True
for label, url in [
    ("Registry Server", f"{REGISTRY}/health"),
    ("System Agent", f"{SYSTEM_AGENT}/health"),
    (f"Ship Middle (:{SHIP_PORT})", f"http://127.0.0.1:{SHIP_PORT}/health"),
    (f"AUV Lower (:{AUV_PORT})", f"http://127.0.0.1:{AUV_PORT}/health"),
    (f"ROV Lower (:{ROV_PORT})", f"http://127.0.0.1:{ROV_PORT}/health"),
]:
    r = http("GET", url)
    alive = r.get("status") == "ok"
    ok = ok and check(label, alive, r.get("agent_id", "") if alive else str(r))

if not ok:
    print("\n⛔ 일부 서비스가 실행되지 않았습니다. SERVER_STARTUP_GUIDE.md를 참고하세요.")
    raise SystemExit(1)

# ──────────────────────────────────────────────────────────
# Step 1. Registry 등록 상태
# ──────────────────────────────────────────────────────────
section("Step 1. Registry 등록 디바이스 확인")

devices = as_list(http("GET", f"{REGISTRY}/devices"))
auv_devices = [d for d in devices if d.get("device_type") == "AUV"]
rov_devices = [d for d in devices if d.get("device_type") == "ROV"]
ship_devices = [d for d in devices if d.get("device_type") == "CONTROL_SHIP"]

check("AUV 등록됨", bool(auv_devices), f"{len(auv_devices)}개")
check("ROV 등록됨", bool(rov_devices), f"{len(rov_devices)}개")
check("Control Ship 등록됨", bool(ship_devices), f"{len(ship_devices)}개")

auv_device = auv_devices[0] if auv_devices else {}
auv_id = auv_device.get("id")
print(f"\n  사용할 AUV: id={auv_id}, name={auv_device.get('name', '')[:30]}")

# 기존 Event/Alert/Mission 수 기록
events_before = len(as_list(http("GET", f"{REGISTRY}/events")))
alerts_before = len(as_list(http("GET", f"{REGISTRY}/alerts")))
proposals_before = len(as_list(http("GET", f"{REGISTRY}/mission-proposals")))
missions_before = len(as_list(http("GET", f"{REGISTRY}/missions")))
print(f"\n  현재 상태: events={events_before}, alerts={alerts_before}, proposals={proposals_before}, missions={missions_before}")

# ──────────────────────────────────────────────────────────
# Step 2. AUV → System Agent: mine_detection event.report
# ──────────────────────────────────────────────────────────
section("Step 2. AUV → System Agent: mine_detection event.report 전송")

scenario_started_at = time.time()
task_id = f"mine-scenario-{int(time.time())}"
scenario_tag = f"scenario_tag:{task_id}"
scenario_frame_id = f"auv-scan-{task_id}"
r = http("POST", f"{SYSTEM_AGENT}/message:send", {
    "taskId": task_id,
    "message": {
        "role": "user",
        "parts": [{
            "type": "data",
            "data": {
                "message_type": "event.report",
                "event_type": "mine_detection",
                "severity": "CRITICAL",
                "device_id": auv_id,
                "device_type": "AUV",
                "location": {"latitude": 37.005, "longitude": 129.425, "depth_m": 15.0},
                "description": f"AUV sonar detected mine-like object at 15m depth ({scenario_tag})",
                "confidence": 0.93,
                "artifacts": [
                    {"type": "mine_location_estimate", "location": {"latitude": 37.005, "longitude": 129.425}, "confidence": 0.93},
                    {"type": "sonar_evidence", "frame_id": scenario_frame_id},
                ],
            },
        }],
    },
})
check("System Agent 수신 완료", r.get("status", {}).get("state") == "completed", f"taskId={r.get('id', '')[:20]}")

# ──────────────────────────────────────────────────────────
# Step 3. Registry: Event 기록 확인
# ──────────────────────────────────────────────────────────
section("Step 3. Registry: Event 기록 확인")
event_wait_seconds = 20
new_events: list[dict[str, Any]] = []
events: list[dict[str, Any]] = []


def parse_ts(iso: str | None) -> float:
    if not iso:
        return 0.0
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0

for _ in range(event_wait_seconds):
    events = as_list(http("GET", f"{REGISTRY}/events"))
    new_events = [
        e for e in events
        if parse_ts(str(e.get("created_at") or "")) >= scenario_started_at - 2
    ]
    tagged = [
        e for e in new_events
        if scenario_frame_id in str((((e.get("metadata") or {}).get("raw_event") or {}).get("artifacts") or []))
    ]
    if tagged:
        new_events = tagged
        break
    time.sleep(1)

check("Event가 새로 기록됨", len(new_events) >= 1, f"{len(new_events)}개 추가")

if new_events:
    ev = sorted(new_events, key=lambda x: x.get("created_at", ""))[-1]
    check("event_type = mine_detection", ev.get("event_type") == "mine_detection", ev.get("event_type"))
    check("severity = CRITICAL", ev.get("severity") == "CRITICAL", ev.get("severity"))
    check("event_id 존재", bool(ev.get("event_id")), ev.get("event_id", "")[:30])
    event_id = ev.get("event_id")
else:
    event_id = None

# ──────────────────────────────────────────────────────────
# Step 4. Registry: Alert 기록 확인
# ──────────────────────────────────────────────────────────
section("Step 4. Registry: Alert 생성 확인")
alert_wait_seconds = 20
new_alerts: list[dict[str, Any]] = []
alerts: list[dict[str, Any]] = []

for _ in range(alert_wait_seconds):
    alerts = as_list(http("GET", f"{REGISTRY}/alerts"))
    new_alerts = alerts[alerts_before:]
    linked_alerts = [a for a in alerts if event_id and a.get("event_id") == event_id]
    selected_alerts = linked_alerts or new_alerts
    if selected_alerts:
        new_alerts = selected_alerts
        break
    time.sleep(1)

check("Alert가 새로 생성됨", len(new_alerts) >= 1, f"{len(new_alerts)}개 추가")

if new_alerts:
    al = sorted(new_alerts, key=lambda x: x.get("created_at", ""))[-1]
    check("severity = CRITICAL", al.get("severity") == "CRITICAL", al.get("severity"))
    if al.get("status") == "waiting" and al.get("alert_id"):
        for _ in range(30):
            refreshed = http("GET", f"{REGISTRY}/alerts/{al.get('alert_id')}")
            if isinstance(refreshed, dict) and refreshed.get("status") in ("processing", "completed", "approved", "dispatched"):
                al = refreshed
                break
            time.sleep(1)

    check("status가 processing/completed", al.get("status") in ("processing", "completed", "approved", "dispatched"), al.get("status"))
    check("alert_id 존재", bool(al.get("alert_id")), al.get("alert_id", "")[:30])
    alert_id = al.get("alert_id")
else:
    alert_id = None

# ──────────────────────────────────────────────────────────
# Step 5. Registry: Mission Proposal / Mission 기록 확인
# ──────────────────────────────────────────────────────────
section("Step 5. Registry: Mission Proposal / Mission 기록 확인")
proposal_wait_seconds = 90
new_proposals: list[dict[str, Any]] = []
new_missions: list[dict[str, Any]] = []

for _ in range(proposal_wait_seconds):
    proposals = as_list(http("GET", f"{REGISTRY}/mission-proposals"))
    missions = as_list(http("GET", f"{REGISTRY}/missions"))
    if alert_id:
        new_proposals = [proposal for proposal in proposals if proposal.get("alert_id") == alert_id]
        new_missions = [mission for mission in missions if mission.get("alert_id") == alert_id]
        if new_proposals or new_missions:
            break
    else:
        new_proposals = proposals[proposals_before:]
        new_missions = missions[missions_before:]
        if new_proposals or new_missions:
            break
    time.sleep(1)

check("Mission Proposal이 생성됨", len(new_proposals) >= 1, f"{len(new_proposals)}개 추가")
check("Mission이 생성됨", len(new_missions) >= 1, f"{len(new_missions)}개 추가")

if new_proposals:
    proposal = sorted(new_proposals, key=lambda x: x.get("created_at", ""))[-1]
    check("proposal.alert_id 연결됨", bool(proposal.get("alert_id")), proposal.get("alert_id", "")[:30])
    check("proposal.steps 존재", bool(proposal.get("steps")), str(proposal.get("steps", []))[:60])

if new_missions:
    mission = sorted(new_missions, key=lambda x: x.get("created_at", ""))[-1]
    check("mission.alert_id 연결됨", bool(mission.get("alert_id")), mission.get("alert_id", "")[:30])
    check(
        "mission.timeline 또는 device_execution_results 존재",
        bool(mission.get("timeline")) or bool(mission.get("device_execution_results")),
        f"timeline={len(mission.get('timeline', []))}, results={len(mission.get('device_execution_results', []))}",
    )

# ──────────────────────────────────────────────────────────
# Step 6. System Agent outbox / device inbox 확인
# ──────────────────────────────────────────────────────────
section("Step 6. System Agent outbox / 하위 agent inbox 확인")

sys_state = http("GET", f"{SYSTEM_AGENT}/state")
outbox = sys_state.get("outbox", [])
check("System Agent outbox에 발송 기록 있음", len(outbox) > 0, f"{len(outbox)}개")

for port, label in [(ROV_PORT, "ROV"), (SHIP_PORT, "Ship"), (AUV_PORT, "AUV")]:
    st = http("GET", f"http://127.0.0.1:{port}/state")
    if "error" not in st:
        inbox = st.get("inbox", [])
        if inbox:
            latest = inbox[-1].get("data", {})
            msg_t = latest.get("message_type") or latest.get("type") or "(unknown)"
            check(f"{label} inbox 수신", True, f"{len(inbox)}개, 최신={msg_t}")
        else:
            check(f"{label} inbox 수신", False, "inbox 비어있음")

# ──────────────────────────────────────────────────────────
# 결과 요약
# ──────────────────────────────────────────────────────────
section("시나리오 완료 — 최종 Registry 상태")

events_after = as_list(http("GET", f"{REGISTRY}/events"))
alerts_after = as_list(http("GET", f"{REGISTRY}/alerts"))
proposals_after = as_list(http("GET", f"{REGISTRY}/mission-proposals"))
missions_after = as_list(http("GET", f"{REGISTRY}/missions"))

latest_alert: dict[str, Any] = {}
latest_proposal: dict[str, Any] = {}
latest_mission: dict[str, Any] = {}
status_snapshot: dict[str, Any] = {}
if alert_id:
    latest_alert, latest_proposal, latest_mission, status_snapshot = poll_latest_completion(alert_id)

proposal_status = str(status_snapshot.get("proposal_status") or latest_proposal.get("status") or "")
mission_status = str(status_snapshot.get("mission_status") or latest_mission.get("status") or "")
alert_status = str(status_snapshot.get("alert_status") or latest_alert.get("status") or "")

print(f"  Events   : {events_before} → {len(events_after)} (+{len(events_after) - events_before})")
print(f"  Alerts   : {alerts_before} → {len(alerts_after)} (+{len(alerts_after) - alerts_before})")
print(f"  Proposals: {proposals_before} → {len(proposals_after)} (+{len(proposals_after) - proposals_before})")
print(f"  Missions : {missions_before} → {len(missions_after)} (+{len(missions_after) - missions_before})")
print()
print("  성공 기준:")
print("  - Event Registry 기록 ✅" if len(events_after) > events_before else "  - Event Registry 기록 ❌")
print("  - Alert 생성 (CRITICAL) ✅" if len(alerts_after) > alerts_before else "  - Alert 생성 ❌")
print("  - Mission Proposal 생성 ✅" if len(proposals_after) > proposals_before else "  - Mission Proposal 생성 ❌")
print("  - Mission 생성 ✅" if len(missions_after) > missions_before else "  - Mission 생성 ❌")
print("  - Alert 최종 완료 ✅" if alert_status == "completed" else f"  - Alert 최종 완료 ❌ ({alert_status or 'unknown'})")
print("  - Proposal 승인/전환 ✅" if proposal_status in {"approved", "converted", "completed"} else f"  - Proposal 승인/전환 ❌ ({proposal_status or 'unknown'})")
print("  - Mission 최종 완료 ✅" if mission_status == "completed" else f"  - Mission 최종 완료 ❌ ({mission_status or 'unknown'})")

overall_success = (
    len(events_after) > events_before
    and len(alerts_after) > alerts_before
    and len(proposals_after) > proposals_before
    and len(missions_after) > missions_before
    and alert_status == "completed"
    and proposal_status in {"approved", "converted", "completed"}
    and mission_status == "completed"
)

if not overall_success:
    raise SystemExit(1)
