# CoWater POC 문서 가이드

## 📚 문서 구조

### 1. [MINE_REMOVAL_GUIDE.md](MINE_REMOVAL_GUIDE.md)

**기뢰 제거 시나리오 가이드 및 스모크 테스트**

**포함 내용**:

- ✅ Moth Heartbeat 실시간 모니터링
- ✅ ROV 유선 연결 강제 (임의 middle layer)
- ✅ AUV 수중음향 조건부 연결
- ✅ A2A 통신 통합 (POC 01-06)
- ✅ 전체 아키텍처
- ✅ 기뢰 제거 시나리오
- ✅ 기본 배포 및 테스트 가이드
- ✅ `run_mine_removal_scenario.py` 로컬 스모크 테스트

**대상**: POC 시스템 기능 및 동작 이해

---

### 2. [run_mine_removal_scenario.py](run_mine_removal_scenario.py)

**외부 서버 없이 기뢰 제거 라우팅을 검증하는 실행 스크립트**

**포함 내용**:

- ✅ AUV 수중 상태에서 middle parent 경유 확인
- ✅ ROV 유선 강제 라우팅 확인
- ✅ Moth track endpoint 충돌 방지 확인
- ✅ 기뢰 제거 작업 순서 출력

**대상**: 빠른 회귀 검증과 데모 전 기본 점검

---

## 🚀 빠른 시작 (3분)

### 1단계: POC 기능 이해

→ [MINE_REMOVAL_GUIDE.md](MINE_REMOVAL_GUIDE.md) 읽기

### 2단계: 시나리오 기본 검증

```bash
python pocs/docs/run_mine_removal_scenario.py --format timeline
```

### 3단계: 실제 서비스 실행

→ [MINE_REMOVAL_GUIDE.md](MINE_REMOVAL_GUIDE.md)의 배포 및 테스트 섹션 참고

---

## 💻 핵심 구현 코드

- **Moth Subscriber**: `pocs/00-device-registration-server/src/transport/moth_subscriber.py`
- **Device Registry**: `pocs/00-device-registration-server/src/registry/device_registry.py`
- **공유 모듈**: `pocs/shared/a2a.py`, `pocs/shared/command.py`
- **모든 POC**: `controller/api.py` (POC 01-06)

---

## 📖 문서 선택 가이드

| 목표                 | 문서                                           |
| -------------------- | ---------------------------------------------- |
| POC 시스템 기능 이해 | [MINE_REMOVAL_GUIDE.md](MINE_REMOVAL_GUIDE.md) |
| 기뢰 제거 기본 검증 | [run_mine_removal_scenario.py](run_mine_removal_scenario.py) |

---

**마지막 업데이트**: 2026-04-29
**상태**: 기뢰 제거 핵심 경로 기본 검증 가능 ✅
