# CoWater PoC - 3D 해양 운영 시각화

미래형 3D 기반 해양 운영 시스템 시각화 검증 프로젝트

## 기능

### 🌊 3D 해양 환경
- **해수면 분계선**: 물 위(Surface)와 물 아래(Underwater)를 명확히 분리
- **동적 파도**: 실시간 Perlin 노이즈 기반 파도 애니메이션
- **수심 깊이**: 최대 -200m까지 지원
- **해저 지형**: 텍스처가 있는 해저면

### 📡 해양 장비 시뮬레이션
**수면 위 (Surface)**
- 🚢 선박 (대형/소형/유조선)
- 🛰️ 드론 / USV (Unmanned Surface Vehicle)
- 📶 통신 타워
- 🏭 통제 센터

**수심 아래 (Underwater)**
- 🤖 ROV (Remotely Operated Vehicle) - 유선 조종
- 🐟 AUV (Autonomous Underwater Vehicle) - 자율 항해
- 🔌 수중 케이블 및 인프라

### 🎮 상호작용
| 컨트롤 | 동작 |
|--------|------|
| **마우스 드래그** | 3D 회전 |
| **마우스 휠** | 줌 인/아웃 |
| **W/A/S/D** | 카메라 좌우 상하 이동 |
| **Space** | 카메라 위로 상승 |
| **Ctrl** | 카메라 아래로 하강 |
| **T** | 시간대 변경 (주간/야간) |
| **P** | 자동 회전 일시정지 |
| **R** | 카메라 초기화 |

### 📊 실시간 UI
- **제어판**: 활성 객체 수, 수심, 날씨, 조명 상태
- **정보판**: 전체 장비 목록 + 좌표 + 수심
- **범례**: 각 객체 타입별 색상 코드
- **단축키 안내**: 조작 가이드

## 구조

```
poc/
├── graphics/
│   └── ocean-visualization.html    ← Three.js 3D 시각화 (독립 실행)
├── scenarios/
│   └── naval-ops.yaml              ← 시뮬레이션 시나리오 정의
├── data/
│   └── objects.json                ← 런타임 객체 상태
└── README.md
```

## 사용 방법

### 1️⃣ 바로 열기 (브라우저)
```bash
# 파일 직접 열기
open /Users/teamgrit/Documents/CoWater/poc/graphics/ocean-visualization.html

# 또는 로컬 서버로 실행 (권장)
cd /Users/teamgrit/Documents/CoWater/poc/graphics
python -m http.server 8000
# http://localhost:8000/ocean-visualization.html
```

### 2️⃣ 기능 확인
- 마우스로 3D 환경을 자유롭게 회전/이동
- 우측 정보판에서 실시간 장비 위치 확인
- 좌측 범례에서 각 객체 타입 구분

## 다음 단계 (검증 후)

### Phase 2: 데이터 바인딩
- [ ] WebSocket 연결 → CoWater `core` API와 실시간 동기화
- [ ] Redis pub/sub → 해양 객체 위치 업데이트
- [ ] 경보 이벤트 → 3D 시각화 반영 (색상/애니메이션 변화)

### Phase 3: 고급 시각화
- [ ] 경로 추적 (Trail) - 각 선박/ROV의 궤적 표시
- [ ] 통신 링크 - 선박↔드론, 센터↔ROV 간 연결선
- [ ] 센서 범위 - ROV/AUV의 스캔 영역 시각화
- [ ] 환경 효과 - 조명/날씨에 따른 수심 가시도 변화

### Phase 4: 분산 배포
- [ ] REST API 엔드포인트 (Node.js Express)
- [ ] 시나리오 기반 자동 시뮬레이션
- [ ] 여러 사용자 동시 접속 (WebGL 클라우드 렌더링)

## 기술 스택

- **Three.js** (r128): 3D 렌더링 엔진
- **OrbitControls.js**: 카메라 인터랙션
- **Vanilla JavaScript**: 상태 관리, UI 업데이트
- **CSS3**: UI 패널 (하이테크 스타일)

## 색상 코드

| 색상 | 의미 |
|------|------|
| 🔴 `#ff6b6b` | 통제 센터 / 타워 |
| 🔵 `#4ecdc4` | 선박 |
| 🟡 `#ffd93d` | 드론 / USV |
| 🟢 `#6bcf7f` | ROV (유선) |
| 🟣 `#95a5ff` | AUV (자율) |
| 🟤 `#8b7355` | 해저 지형 |

## 성능 지표

- FPS: 60 (대부분의 최신 브라우저)
- 객체 수: 최대 100+ (성능 저하 없음)
- 파도 해상도: 128x128 (부드러운 물결)

## 문제 해결

### 3D 장면이 검은색으로 보임
- 조명이 꺼져있을 수 있음
- 브라우저 콘솔에서 에러 확인: `F12` → Console

### 마우스가 반응 안 함
- OrbitControls 로드 확인
- 브라우저의 Three.js CDN 접근성 확인

### 객체가 안 보임
- 카메라를 초기화: `R` 키 누르기
- 줌 아웃: 마우스 휠 아래로

---

**다음 검증 대상**: 
1. ✅ 3D 해양 환경 렌더링
2. ⏳ 실시간 데이터 바인딩
3. ⏳ 복수 사용자 동시 접속
4. ⏳ 모바일 반응형 지원
