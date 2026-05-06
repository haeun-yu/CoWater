# CoWater 기뢰 탐지·제거 시나리오 — 작업 인수인계 문서

> 브랜치: `improve/features`  
> 최종 검증일: 2025-05  
> 검증 결과: **RUN 1 ✅ / RUN 2 ✅** (연속 2회 성공)

---

## 1. 무엇을 했는가

### 핵심 버그 수정

| 파일 | 수정 내용 |
|------|-----------|
| `server/registration/src/core/models.py` | `DeviceRecord.to_dict()`에 `registry_id`(숫자 내부 ID) 필드 추가 |
| `server/system-agent/agent/runtime.py` | `_send_a2a_task()`에서 `id(public)` 대신 `registry_id` 기반 포트 매핑으로 전환; `_device_id()` 헬퍼 도입 |
| `server/system-agent/agent/runtime.py` | waiting alerts 정렬: 심각도 우선 + 최신 우선(`_parse_iso_ts`) |
| `server/system-agent/agent/runtime.py` | **30분 초과 alerts 스킵** + **루프당 최대 3개 처리** (백로그 누적 방지) |
| `server/system-agent/agent/llm_client.py` | LLM 예외 상세 로그(type/repr/traceback) |
| `server/system-agent/config.json` | `timeout_seconds` 30 → 120 |
| `device/configs/*.json` | 모든 device agent timeout 120s 상향 |

### 테스트 스크립트 안정화 (`docs/run_mine_removal_scenario.py`)

- `scenario_frame_id = f"auv-scan-{task_id}"` 기반으로 Event를 정확히 식별 (이전에는 description 텍스트 검색으로 오탐 가능)  
- Step4: `event_id` 연동 alert 우선 탐색  
- Step5: `alert_id` 기반 response 검색 + polling 90초  
- `dispatch_result` 내 `steps[]`, `task_results[]`, fallback 방식으로 `delivered` 여부 판별 보강  
- `as_list()` 헬퍼로 API 응답이 dict/list 혼용일 때 안전하게 처리

---

## 2. 현재 상태

### 성공하는 것

- **AUV → mine_detection → System Agent → Registry → Alert → ROV/AUV 작업 할당** 전체 흐름이 AI(LLM) 기반으로 동작
- 연속 실행 2회 모두 `dispatch delivered=True`, Response 연결 확인됨

### 알려진 한계

| 항목 | 설명 |
|------|------|
| `Step 4: status = waiting` | Alert의 `status` 필드가 `approved`/`dispatched`로 변경되지 않는 경우 있음. 실제로는 LLM이 처리해 Response가 생성되므로 기능에는 문제 없음. Registry의 alert status 갱신 로직 개선 여지 있음 |
| `Ship inbox 비어있음` | Ship 에이전트는 이 시나리오의 직접 대상이 아님. USV/ROV/AUV 중심으로 정상 동작 중 |
| LLM 처리 지연 | Ollama `gemma4:e2b` 모델이 로컬에서 실행되어 응답에 30~90초 소요 가능 |
| 백로그 alert 재시작 시 처리 | System Agent 재시작 시 최근 30분 내 alerts만 처리함 (의도적 설계) |

---

## 3. 재현 절차 (집에서 처음 실행할 경우)

### 사전 요구사항

```bash
# 가상환경 생성 및 패키지 설치
python3 -m venv .venv
.venv/bin/pip install httpx requests fastapi uvicorn pydantic
# Ollama 설치 후 모델 pull
ollama pull gemma4:e2b   # 또는 사용 가능한 모델
```

### 서비스 시작 순서

```bash
# 1. Registry 서버 (포트 8280)
cd server/registration
.venv/bin/python device_registration_server.py &

# 2. Device Agents
cd /path/to/CoWater
.venv/bin/python device/device_agent.py --config device/configs/usv-lower.json &   # 포트 9110
.venv/bin/python device/device_agent.py --config device/configs/usv-middle.json &  # 포트 9111
.venv/bin/python device/device_agent.py --config device/configs/auv-lower.json &   # 포트 9112
.venv/bin/python device/device_agent.py --config device/configs/rov-lower.json &   # 포트 9113
.venv/bin/python device/device_agent.py --config device/configs/ship-middle.json & # 포트 9115

# 3. System Agent (포트 9116) — 반드시 device들이 등록된 후 시작
mkdir -p .logs
.venv/bin/python server/system-agent/system_agent.py > .logs/System-Agent.log 2>&1 &
```

또는 통합 스크립트 사용:
```bash
bash START_SERVICES.sh
```

### 시나리오 테스트

```bash
# 단일 실행
.venv/bin/python docs/run_mine_removal_scenario.py

# 연속 2회 실행 (System Agent 재시작 포함)
bash .run_test.sh
```

### 서비스 상태/중지

```bash
bash STATUS_SERVICES.sh
bash STOP_SERVICES.sh
```

---

## 4. 남은 과제 (이어서 할 일)

1. **Registry alert status 갱신 로직 개선**  
   - System Agent가 LLM으로 처리·Response 생성 후 Registry의 alert status를 `approved`/`dispatched`로 업데이트하는 코드 경로 확인 및 보강  
   - 파일: `server/system-agent/agent/runtime.py` → `_process_alert()` 내 `acknowledge_alert()` 호출 확인

2. **USV 중간 계층 미션 릴레이 검증**  
   - 현재 Ship inbox가 비어있음. USV-middle이 ROV에 대한 중간 릴레이 역할을 하는지 E2E 검증 필요

3. **Ollama 모델 교체 고려**  
   - `gemma4:e2b`는 로컬 추론이 느림. 더 빠른 모델(`llama3.2:3b`, `qwen2.5:3b` 등) 또는 외부 API 연동 고려

4. **Registry 데이터 초기화 기능**  
   - 테스트 반복 시 누적된 수백 개의 alerts/responses를 초기화하는 엔드포인트 또는 스크립트 필요  
   - 현재는 서비스 재시작으로 메모리 초기화

5. **httpx 의존성 명시**  
   - `server/system-agent/requirements.txt`에 `httpx` 추가 필요

---

## 5. 주요 파일 위치

```
server/
  registration/
    device_registration_server.py   # Registry API 서버
    src/core/models.py              # DeviceRecord.to_dict() — registry_id 추가
  system-agent/
    system_agent.py                 # System Agent 진입점
    agent/runtime.py                # Alert 처리 루프, LLM 판단, A2A 발송
    agent/llm_client.py             # Ollama 호출 클라이언트
    config.json                     # LLM endpoint, timeout 설정
device/
  device_agent.py                   # Device Agent 진입점
  configs/                          # 각 device 설정 (포트, LLM, timeout)
docs/
  run_mine_removal_scenario.py      # E2E 시나리오 테스트 스크립트
  HANDOFF_NOTES.ko.md               # 이 문서
.run_test.sh                        # 연속 2회 실행 + SA 재시작 래퍼
.logs/                              # 각 서비스 로그 파일
```

---

## 6. 체크리스트

```
재현 시 확인 항목:
[ ] Ollama 실행 중 & 모델 로드 완료 (ollama list)
[ ] Registry 서버 :8280 응답 확인 (curl http://127.0.0.1:8280/health)
[ ] Device agents :9112, :9113, :9115 응답 확인
[ ] System Agent :9116 응답 확인 (curl http://127.0.0.1:9116/health)
[ ] python docs/run_mine_removal_scenario.py 실행 후
    - Event Registry 기록 ✅
    - Alert 생성 (CRITICAL) ✅
    - Response 연결 ✅ 확인
```
