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

devices = http("GET", f"{REGISTRY}/devices")
auv_devices = [d for d in devices if d.get("device_type") == "AUV"]
rov_devices = [d for d in devices if d.get("device_type") == "ROV"]
ship_devices = [d for d in devices if d.get("device_type") == "CONTROL_SHIP"]

check("AUV 등록됨", bool(auv_devices), f"{len(auv_devices)}개")
check("ROV 등록됨", bool(rov_devices), f"{len(rov_devices)}개")
check("Control Ship 등록됨", bool(ship_devices), f"{len(ship_devices)}개")

auv_device = auv_devices[0] if auv_devices else {}
auv_id = auv_device.get("id")
print(f"\n  사용할 AUV: id={auv_id}, name={auv_device.get('name', '')[:30]}")

# 기존 Event/Alert/Response 수 기록
events_before = len(http("GET", f"{REGISTRY}/events"))
alerts_before = len(http("GET", f"{REGISTRY}/alerts"))
responses_before = len(http("GET", f"{REGISTRY}/responses"))
print(f"\n  현재 상태: events={events_before}, alerts={alerts_before}, responses={responses_before}")

# ──────────────────────────────────────────────────────────
# Step 2. AUV → System Agent: mine_detection event.report
# ──────────────────────────────────────────────────────────
section("Step 2. AUV → System Agent: mine_detection event.report 전송")

task_id = f"mine-scenario-{int(time.time())}"
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
                "description": "AUV sonar detected mine-like object at 15m depth",
                "confidence": 0.93,
                "artifacts": [
                    {"type": "mine_location_estimate", "location": {"latitude": 37.005, "longitude": 129.425}, "confidence": 0.93},
                    {"type": "sonar_evidence", "frame_id": f"auv-scan-{int(time.time())}"},
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
time.sleep(1)

events = http("GET", f"{REGISTRY}/events")
new_events = events[events_before:]
check("Event가 새로 기록됨", len(new_events) >= 1, f"{len(new_events)}개 추가")

if new_events:
    ev = new_events[-1]
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
time.sleep(1)

alerts = http("GET", f"{REGISTRY}/alerts")
new_alerts = alerts[alerts_before:]
check("Alert가 새로 생성됨", len(new_alerts) >= 1, f"{len(new_alerts)}개 추가")

if new_alerts:
    al = new_alerts[-1]
    check("severity = CRITICAL", al.get("severity") == "CRITICAL", al.get("severity"))
    check("status가 approved/dispatched", al.get("status") in ("approved", "dispatched", "completed"), al.get("status"))
    check("alert_id 존재", bool(al.get("alert_id")), al.get("alert_id", "")[:30])
    alert_id = al.get("alert_id")
else:
    alert_id = None

# ──────────────────────────────────────────────────────────
# Step 5. Registry: Response 기록 확인
# ──────────────────────────────────────────────────────────
section("Step 5. Registry: Response 기록 확인")
time.sleep(2)

responses = http("GET", f"{REGISTRY}/responses")
new_responses = responses[responses_before:]
check("Response가 새로 생성됨", len(new_responses) >= 1, f"{len(new_responses)}개 추가")

if new_responses:
    resp = new_responses[-1]
    check("alert_id 연결됨", bool(resp.get("alert_id")), resp.get("alert_id", "")[:30])
    check("dispatch_result 존재", bool(resp.get("dispatch_result")), str(resp.get("dispatch_result", {}))[:60])

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

events_after = http("GET", f"{REGISTRY}/events")
alerts_after = http("GET", f"{REGISTRY}/alerts")
responses_after = http("GET", f"{REGISTRY}/responses")

print(f"  Events   : {events_before} → {len(events_after)} (+{len(events_after) - events_before})")
print(f"  Alerts   : {alerts_before} → {len(alerts_after)} (+{len(alerts_after) - alerts_before})")
print(f"  Responses: {responses_before} → {len(responses_after)} (+{len(responses_after) - responses_before})")
print()
print("  성공 기준:")
print("  - Event Registry 기록 ✅" if len(events_after) > events_before else "  - Event Registry 기록 ❌")
print("  - Alert 생성 (CRITICAL) ✅" if len(alerts_after) > alerts_before else "  - Alert 생성 ❌")
print("  - Response 연결 ✅" if len(responses_after) > responses_before else "  - Response 연결 ❌")
