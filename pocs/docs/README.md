# CoWater 기뢰 제거 시나리오 문서

## 📚 문서

### [MINE_REMOVAL_GUIDE.md](MINE_REMOVAL_GUIDE.md)
**완전한 기뢰 제거 시나리오 가이드** (모든 내용 통합)

**포함 내용**:
- ✅ Moth Heartbeat 실시간 모니터링
- ✅ ROV 유선 연결 강제 (임의 middle layer)
- ✅ AUV 수중음향 조건부 연결
- ✅ A2A 통신 통합 (POC 01-06)
- ✅ 전체 아키텍처
- ✅ 기뢰 제거 시나리오
- ✅ 배포 및 테스트 가이드

---

## 🚀 빠른 시작

### 1단계: 개요 이해
`MINE_REMOVAL_GUIDE.md` → **시스템 개요** 섹션

### 2단계: 핵심 기능 학습
`MINE_REMOVAL_GUIDE.md` → **핵심 기능** 섹션

### 3단계: 배포 및 테스트
`MINE_REMOVAL_GUIDE.md` → **배포 및 테스트** 섹션

---

## 💻 구현 코드

- **Moth Subscriber**: `pocs/00-device-registration-server/src/transport/moth_subscriber.py`
- **Device Registry**: `pocs/00-device-registration-server/src/registry/device_registry.py`
- **공유 모듈**: `pocs/shared/a2a.py`, `pocs/shared/command.py`
- **모든 POC**: `controller/api.py` (01-06)

---

**마지막 업데이트**: 2026-04-28
