# CoWater POC 문서 가이드

## 📚 문서 구조

### 1. [MINE_REMOVAL_GUIDE.md](MINE_REMOVAL_GUIDE.md)

**완전한 기뢰 제거 시나리오 가이드**

**포함 내용**:

- ✅ Moth Heartbeat 실시간 모니터링
- ✅ ROV 유선 연결 강제 (임의 middle layer)
- ✅ AUV 수중음향 조건부 연결
- ✅ A2A 통신 통합 (POC 01-06)
- ✅ 전체 아키텍처
- ✅ 기뢰 제거 시나리오
- ✅ 기본 배포 및 테스트 가이드

**대상**: POC 시스템 기능 및 동작 이해

---

### 2. [DEPLOYMENT.md](DEPLOYMENT.md)

**배포 및 운영 완전 가이드**

**포함 내용**:

- ✅ 로컬 개발 환경 (단일 호스트)
- ✅ 분산 배포 (멀티 호스트)
- ✅ SSH 터널 원격 접근
- ✅ 클라우드 배포 (AWS/Azure)
- ✅ 시뮬레이터 실행 (4가지 시나리오)
- ✅ 보안 설정 체크리스트
- ✅ 트러블슈팅 가이드

**대상**: 배포, 운영, 확장, 보안 설정

---

## 🚀 빠른 시작 (3분)

### 1단계: POC 기능 이해

→ [MINE_REMOVAL_GUIDE.md](MINE_REMOVAL_GUIDE.md) 읽기

### 2단계: 배포 선택

→ [DEPLOYMENT.md](DEPLOYMENT.md)에서 적절한 시나리오 선택

### 3단계: 실행 및 테스트

→ 선택한 시나리오의 단계별 명령 실행

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

---

**마지막 업데이트**: 2026-04-28  
**상태**: 모든 배포 시나리오 + POC 기능 문서 완성 ✅
