# Integrated Marine Platform Simulator

실시간 선박 시뮬레이터와 해양 관제 플랫폼을 한 화면에서 실행하는 1단계 데모입니다.

현재 구조는 다음과 같습니다.

- 분리된 시뮬레이터 프로세스가 AIS NMEA 배치를 생성
- `wss://cobot.center:8287` Moth 서버로 시뮬레이터가 publish
- 브라우저 클라이언트는 같은 Moth 서버를 subscribe해서 선박 상태를 갱신

## 포함 기능

- 5척의 선박 시뮬레이션
- AIS NMEA 형태의 프레임 생성 및 파싱
- 지도 위 실시간 선박 표시
- 좌측 선박 요약 목록
- 선박 선택 시 좌측 상세 정보 패널 전환
- 뒤로가기 버튼으로 선택 해제

## 실행

```bash
npm install
npm run start
```

기본 실행 포트는 다음과 같습니다.

- UI: `5005`
- preview: `7001`

기본 Moth 주소는 `wss://cobot.center:8287`입니다.
필요하면 `MOTH_PUB_URL`, `VITE_MOTH_SUB_URL` 환경변수로 덮어쓸 수 있습니다.

## 구현 메모

- `src/lib/simulator.ts`: 선박 이동, 속도/침로 변화, AIS 프레임 발생
- `src/lib/ais.ts`: NMEA 구조의 문장 생성과 복원
- `src/lib/aisStream.ts`: AIS 배치 직렬화/복원, 프레임을 선박 상태로 반영
- `server/simulator-publisher.ts`: 외부 시뮬레이터 publisher
- `src/App.tsx`: moth subscriber, 지도, 좌측 패널, 상세 보기, 실시간 스트림 UI

로컬 브리지 실험이 필요하면 `npm run dev:moth`로 [server/moth-bridge.ts](/Users/teamgrit/conductor/workspaces/CoWater/luxembourg/server/moth-bridge.ts)를 따로 띄울 수 있습니다.

현재 AIS 메시지는 데모 목적의 경량 `!AIVDM` 구조를 사용합니다. 이후 단계에서 실제 6-bit AIS payload 인코더/디코더로 교체할 수 있도록 생성과 파싱 로직을 분리해 두었습니다.
