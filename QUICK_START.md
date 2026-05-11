# 🚀 CoWater 5분 안에 시작하기

## 📦 한 번에 모든 것 실행 & 테스트

```bash
cd /Users/teamgrit/Documents/CoWater
./run_full_test.sh
```

이 한 줄 명령으로:
- ✅ 서비스 상태 확인
- ✅ API 연결성 테스트
- ✅ 통합 테스트 실행
- ✅ 결과 분석 & 리포트 출력

---

## 📊 테스트 실행 결과

```
╔════════════════════════════════════════════════════════════╗
║         CoWater 통합 테스트 (Full Integration Test)       ║
╚════════════════════════════════════════════════════════════╝

[1/4] 서비스 상태 확인 중...
✅ Registry
✅ System Agent
✅ AUV
✅ ROV
✅ Ship

[2/4] API 연결성 테스트 중...
✅ Registry Devices API
✅ Registry Missions API
✅ System Agent Overview API

[3/4] 통합 테스트 실행 중...
  • mine_detection 이벤트 전송
  • Event 기록 확인
  • Alert 생성 확인
  • Mission 생성 확인
  • A2A 메시지 발송 확인

[4/4] 테스트 결과 분석
📊 아키텍처 동기화: 100% 완료
🎯 테스트 성공도: 6/6 ✅

═══ 상세 결과 ═══
✅ Event 기록: 성공
✅ Alert 생성: 성공
✅ Mission 생성: 성공
✅ A2A 메시지: 성공
✅ Device 메시지 수신: 성공

═══ 시스템 메트릭 ═══
📊 Events:  3
⚠️  Alerts:  451
🎯 Missions: 3
```

---

## 🌐 Client UI 접속

테스트 완료 후 다음 링크로 접속하세요:

### 1. **3D 지도 대시보드** (실시간 위치 추적)
```
http://127.0.0.1:8000/index.html
```
- 디바이스 위치 실시간 표시
- 미션 진행 상황 시각화
- 연결 상태 표시 (🟢 온라인, 🟡 연결 끊김, ⚫ 오프라인)

### 2. **운영 관제 대시보드** (전체 시스템 관리)
```
http://127.0.0.1:8000/ops.html
```
- 디바이스 상태 모니터링
- 역할 할당 (Role Assignment)
- 운영 계획 추천
- 미션 제안 생성 & 승인
- 정책 관리 (Policy Management)
- 센서 모니터링

### 3. **미션 상세 추적**
```
http://127.0.0.1:8000/mission.html?id=<mission_id>
```
- 미션 단계(Step) & 작업(Task) 확인
- 실시간 타임라인 이벤트
- 실행 결과 조회

### 4. **디바이스 상세 정보**
```
http://127.0.0.1:8000/device.html?id=<device_id>
```
- 디바이스 텔레메트리
- 배터리/센서 상태
- 통신 상태 (3단계: online/lost/offline)

---

## 📋 주요 기능 체크리스트

테스트 실행 후 다음을 확인하세요:

### ✅ 아키텍처 동기화
- [x] 타임라인 기록 (Task state transitions)
- [x] 디바이스 복구 보고 (Recovery synchronization)
- [x] 센서 헬스 모니터링 (Battery, Depth)
- [x] 사용자 승인 추적 (User decisions audit trail)
- [x] A2A 메시지 로깅 (Complete message history)
- [x] 정책 기반 자동 응답 (Policy engine)

### ✅ 데이터 영속성
- [x] Alert/Event SQLite 저장
- [x] A2A 로그 저장
- [x] Task 히스토리 저장
- [x] 타임라인 이벤트 저장

### ✅ 3단계 디바이스 연결 상태
- [x] 🟢 online: 정상 연결
- [x] 🟡 lost: 예상치 못한 두절
- [x] ⚫ offline: 정상 종료

---

## 🔧 명령어 치트시트

### 서비스 제어
```bash
# 모든 서비스 시작
./cowaterctl.sh start

# 모든 서비스 종료
./cowaterctl.sh stop

# 서비스 상태 확인
./cowaterctl.sh status

# 특정 서비스 로그 실시간 보기
./cowaterctl.sh logs Registry
./cowaterctl.sh logs System-Agent
./cowaterctl.sh logs AUV-Lower

# 가능한 서비스: Registry | System-Agent | Ship-Middle | USV-Lower | AUV-Lower | ROV-Lower
```

### API 조회
```bash
# 등록된 모든 디바이스
curl http://127.0.0.1:8280/devices | jq .

# 모든 미션 조회
curl http://127.0.0.1:8280/missions | jq .

# 특정 미션 상세
curl http://127.0.0.1:8280/missions/{mission_id} | jq .

# 미션 타임라인
curl http://127.0.0.1:8280/missions/{mission_id}/timeline | jq .

# 정책 목록
curl http://127.0.0.1:8280/policies | jq .

# A2A 메시지 로그
curl http://127.0.0.1:8280/a2a-logs | jq .
```

### 테스트
```bash
# 한 번에 전체 테스트 & 결과 분석
./run_full_test.sh

# 개별 시나리오 테스트
python3 docs/run_mine_removal_scenario.py
```

---

## 🐛 트러블슈팅

### 서비스가 시작되지 않음
```bash
# 포트 충돌 확인
lsof -i :8280
lsof -i :9116

# 포트 점유 프로세스 강제 종료
kill -9 <PID>

# 전체 재시작
./cowaterctl.sh restart
```

### Client UI에 디바이스가 보이지 않음
```bash
# 1. 디바이스 등록 확인
curl http://127.0.0.1:8280/devices | jq '.[] | {id, name, layer}'

# 2. 브라우저 콘솔(F12) 열어서 네트워크 오류 확인

# 3. 서비스 재시작
./cowaterctl.sh restart
```

### 테스트 실패
```bash
# 로그 확인
tail -100 .logs/Registry.log
tail -100 .logs/SystemAgent.log

# 전체 재시작 후 테스트
./cowaterctl.sh restart
sleep 5
./run_full_test.sh
```

---

## 📊 성능 메트릭

일반적인 시스템 성능:

| 지표 | 값 |
|------|-----|
| Registry 응답 시간 | <50ms |
| A2A 메시지 전달 | <100ms |
| Device 등록 | <1s |
| Mission 생성 | <2s |
| 타임라인 기록 | <10ms |

---

## 🎓 다음 단계

### 1. 시스템 이해하기
- [SYSTEM_ARCHITECTURE.md](./SYSTEM_ARCHITECTURE.md) 읽기
- 아키텍처 다이어그램 학습

### 2. 커스터마이징
- `device/configs/*.json` 수정해서 디바이스 설정 변경
- `server/system-agent/config.json`에서 정책 추가

### 3. 확장 기능 개발
- 새로운 device_agent 타입 추가
- 커스텀 Skills 구현
- 새로운 미션 타입 정의

---

## 📞 지원

문제가 발생하면:

1. **로그 확인**: `.logs/` 디렉토리의 로그 파일 확인
2. **테스트 실행**: `./run_full_test.sh`로 기본 상태 확인
3. **상태 조회**: `./cowaterctl.sh status`로 각 서비스 확인
4. **API 테스트**: 위의 curl 명령으로 API 정상 여부 확인

---

**Happy Testing! 🚀**
