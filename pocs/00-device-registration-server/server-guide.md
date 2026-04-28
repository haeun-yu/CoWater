# 디바이스 등록 및 사용 가이드

이 문서는 CoBiz 시스템에서 로봇 디바이스를 등록하고 사용하는 방법을 설명합니다. 시각화 기능을 제외한 디바이스 등록 프로세스, 디바이스 구성, 그리고 기본 사용 방법을 다룹니다.

---

## 0. 설정 방법

서버 설정은 `config.json`을 기본으로 읽고, 같은 항목이 있으면 환경변수가 우선합니다.

### 0.1 `config.json`

기본 파일 위치:

```text
pocs/00-device-registration-server/config.json
```

예시:

```json
{
  "device": {
    "secret_key": "server-secret"
  },
  "server": {
    "host": "192.168.1.100",
    "port": 9001,
    "ping_endpoint": "/pang/ping"
  },
  "agent": {
    "scheme": "ws",
    "host": "127.0.0.1",
    "port": 9010,
    "path_prefix": "/agents",
    "command_scheme": "http",
    "command_path_prefix": "/agents"
  },
  "cors": {
    "allow_origins": ["*"]
  }
}
```

### 0.2 환경변수

- `COWATER_DEVICE_CONFIG_PATH`
- `COWATER_DEVICE_SECRET_KEY`
- `COWATER_DEVICE_SERVER_HOST`
- `COWATER_DEVICE_SERVER_PORT`
- `COWATER_DEVICE_PING_ENDPOINT`
- `COWATER_DEVICE_AGENT_SCHEME`
- `COWATER_DEVICE_AGENT_HOST`
- `COWATER_DEVICE_AGENT_PORT`
- `COWATER_DEVICE_AGENT_PATH_PREFIX`
- `COWATER_DEVICE_AGENT_COMMAND_SCHEME`
- `COWATER_DEVICE_AGENT_COMMAND_PATH_PREFIX`
- `COWATER_DEVICE_CORS_ORIGINS`

### 0.3 우선순위

1. 환경변수
2. `config.json`
3. 코드 기본값

### 0.4 실행 예시

기본 실행:

```bash
cd pocs/00-device-registration-server
python3 src/device_registration_server.py
```

설정 파일 경로를 바꾸고 싶을 때:

```bash
COWATER_DEVICE_CONFIG_PATH=./my-config.json python3 src/device_registration_server.py
```

## 1. 디바이스 등록 프로세스

### 1.1 등록 요청 (Device Registration)

#### 엔드포인트
```
POST /devices
```

#### 요청 본문
```json
{
  "secretKey": "string",
  "name": "string",
  "tracks": [
    {
      "type": "VIDEO|LIDAR|AUDIO|CONTROL|BATTERY|SPEAKER|TOPIC|MAP|ODOMETRY|GPS|TRAJECTORY",
      "name": "string",
      "endpoint": "string"
    }
  ],
  "actions": {
    "core": ["SLAM_NAVIGATION", "MAP_NAVIGATION", "GPS_NAVIGATION", "NAVIGATION_3D", "TTS", "PARKING"],
    "custom": ["string"]
  }
}
```

#### 보안 검증
1. **Secret Key 검증**: 요청의 `secretKey`가 서버 설정의 `device.secretKey`와 일치해야 함
2. **이름 중복 검사**: 같은 이름의 디바이스가 이미 존재하면 등록 실패

#### 응답 (201 Created)
```json
{
  "id": 1,
  "name": "robot-1",
  "token": "generated-token-string",
  "agent": {
    "scheme": "ws",
    "host": "127.0.0.1",
    "port": 9010,
    "path_prefix": "/agents",
    "command_scheme": "http",
    "command_path_prefix": "/agents",
    "endpoint": "ws://127.0.0.1:9010/agents/generated-token-string",
    "command_endpoint": "http://127.0.0.1:9010/agents/generated-token-string/command",
    "connected": false
  },
  "connected": false
}
```

#### 생성되는 것
- 디바이스 고유 ID (Long)
- 고유 토큰 (UUID 기반): 디바이스 인증 및 통신용
- Agent 주소: 디바이스별 Agent 연결용 WebSocket 주소
- Agent 명령 주소: 원격 제어용 HTTP 엔드포인트
- 기본 메인 비디오 트랙: VIDEO 타입 트랙 중 첫 번째가 자동 설정
- 연결 상태: 기본값 false (미연결)

### 1.2 Agent 등록/연결 정보

디바이스가 등록된 뒤, 각 디바이스별 Agent는 `PUT /devices/{deviceId}/agent`로 자기 연결 정보를 다시 서버에 등록합니다.

#### 엔드포인트
```http
PUT /devices/{deviceId}/agent
```

#### 요청 본문
```json
{
  "secretKey": "server-secret",
  "endpoint": "ws://127.0.0.1:9010/agents/generated-token-string",
  "commandEndpoint": "http://127.0.0.1:9010/agents/generated-token-string/command",
  "llm_enabled": true,
  "connected": true,
  "last_seen_at": "2026-04-23T12:00:00+09:00"
}
```

#### 의미
- `endpoint`: Agent가 디바이스 스트림과 연결되는 WebSocket 주소
- `commandEndpoint`: 원격 사용자가 Agent에 명령을 보낼 때 쓰는 HTTP 주소
- `llm_enabled`: 이 Agent가 LLM 기반 hybrid 판단을 사용하는지 여부
- `role`: Agent 역할 식별자. 예: `system_center`, `regional_orchestrator`, `mission_orchestrator`, `device_agent`, `usv`, `auv`, `rov`
- `skills`: 이 Agent가 수행할 수 있는 작업 이름 목록
- `available_actions`: 실제 명령으로 허용할 액션 이름 목록
- `connected`: 현재 연결 여부
- `last_seen_at`: 마지막으로 확인된 시간

이 서버는 판단용으로 필요한 최소 정보만 저장합니다.  
상세 제약이나 장황한 설명은 Agent 쪽 `AGENT.md`와 `manifest`에서 관리하고, 03 서버는 라우팅과 연결 판단에 필요한 값만 유지합니다.

### 1.3 알림/대응 원장

03 서버는 디바이스 등록 원장 외에도 시스템 알림과 대응 기록의 canonical store 역할을 합니다.

#### 엔드포인트
```http
POST /alerts/ingest
GET /alerts
GET /alerts/{alert_id}
POST /alerts/{alert_id}/ack
POST /responses/ingest
GET /responses
GET /responses/{response_id}
```

#### 의미
- `alerts`: 시스템 이벤트 분석 결과로 생성된 알림
- `responses`: 알림에 대한 자동/수동 대응 기록
- `ack`: 사용자 승인/반려 상태 기록

06 시스템 Agent는 알림을 생성하면 이 원장으로 게시하고, 사용자 승인이나 대응 결과가 생기면 같은 원장에 갱신합니다.

Agent가 연결이 끊기면 `DELETE /devices/{deviceId}/agent?secretKey=...`로 연결 해제 상태를 저장합니다.

---

## 2. 디바이스 구성 (Device Architecture)

### 2.1 디바이스 기본 정보

```typescript
type Device = {
  id: number                           // 디바이스 고유 ID
  name: string                         // 디바이스 이름
  connected: boolean                   // 연결 상태
  created_at: string                   // 생성 시간
  main_video_track_name?: string      // 메인 비디오 트랙 (NULL 가능)
  server: DeviceServerInformation     // 디바이스 서버 정보
  tracks: DeviceModule[]              // 디바이스 모듈/트랙
  actions?: DeviceAction              // 디바이스 지원 액션
}
```

### 2.2 디바이스 모듈 (Tracks)

디바이스는 여러 모듈(트랙)로 구성되며, 각 모듈은 특정 기능을 담당합니다.

#### 지원 모듈 타입

| 타입 | 설명 | 방향성 | 용도 |
|------|------|--------|------|
| **VIDEO** | 비디오 스트림 | 단방향 (디바이스→서버) | 실시간 영상 스트리밍 |
| **LIDAR** | 라이다 센서 | 단방향 (디바이스→서버) | 3D 환경 스캔 |
| **AUDIO** | 오디오 스트림 | 단방향 (디바이스→서버) | 음성 수신 |
| **CONTROL** | 제어 신호 | 양방향 | 로봇 제어 명령 수신 |
| **BATTERY** | 배터리 상태 | 단방향 (디바이스→서버) | 배터리 모니터링 |
| **SPEAKER** | 스피커 제어 | 단방향 (서버→디바이스) | TTS 및 음성 출력 |
| **TOPIC** | 토픽 데이터 | 양방향 | 일반 데이터 토픽 |
| **MAP** | 지도 데이터 | 단방향 (디바이스→서버) | 작성된 지도 전달 |
| **ODOMETRY** | 위치 정보 | 단방향 (디바이스→서버) | 로봇 위치/방향 |
| **GPS** | GPS 위치 | 단방향 (디바이스→서버) | 글로벌 위치 정보 |
| **TRAJECTORY** | 이동 궤적 | 단방향 (디바이스→서버) | 로봇 이동 경로 |

#### 모듈 구조

```typescript
type DeviceModule = {
  type: DeviceModuleType        // 모듈 타입
  name: string                  // 모듈 이름 (고유)
  endpoint: string              // WebSocket 엔드포인트 경로
}
```

#### 엔드포인트 생성 규칙

각 모듈의 WebSocket 엔드포인트는 다음 형식으로 생성됩니다:

```
/pang/ws/meb?channel=instant&name={token}&source=base&track={track_name_lowercase}
```

**예시:**
```
# 비디오 스트림
/pang/ws/meb?channel=instant&name=abc123def&source=base&track=video_main

# 제어 신호
/pang/ws/meb?channel=instant&name=abc123def&source=base&track=control
```

### 2.3 디바이스 액션 (Actions)

디바이스가 지원하는 기능과 작업을 정의합니다.

```typescript
type DeviceAction = {
  core: DeviceActionType[]      // 핵심 액션
  custom: string[]              // 커스텀 액션
}

type DeviceActionType =
  | 'SLAM_NAVIGATION'           // SLAM 기반 자율 네비게이션
  | 'MAP_NAVIGATION'            // 사전 작성 지도 기반 네비게이션
  | 'GPS_NAVIGATION'            // GPS 기반 네비게이션
  | 'NAVIGATION_3D'             // 3D 환경 네비게이션
  | 'TTS'                       // 음성 합성 출력
  | 'PARKING'                   // 주차/복귀 기능
```

---

## 3. 디바이스 생명주기 관리

### 3.1 디바이스 상태 전이

```
등록 (Created)
    ↓
연결 (Connected) :left_right_arrow: 미연결 (Disconnected)
    ↓
삭제 (Deleted)
```

#### 상태 전이 이벤트

| 이벤트 | 발생 시기 | 처리 내용 |
|--------|----------|---------|
| `DeviceRegisteredEvent` | 디바이스 등록 완료 시 | 이벤트 발행 |
| `DeviceConnectedEvent` | 디바이스 연결 시 | 상태 변경, 이벤트 발행 |
| `DeviceDisconnectedEvent` | 디바이스 연결 해제 시 | 상태 변경, 이벤트 발행 |

### 3.2 연결 상태 관리

#### 서버 시작 시
```java
// 서버 시작 시 모든 디바이스를 미연결 상태로 초기화
updateAllDevicesAsDisconnected()
```

#### 디바이스 연결/해제
```java
// 디바이스 연결
device.connect()      // → DeviceConnectedEvent 발행

// 디바이스 해제
device.disconnect()   // → DeviceDisconnectedEvent 발행
```

---

## 4. 디바이스 조회 API

### 4.1 전체 디바이스 목록 조회

#### 엔드포인트
```
GET /devices
```

#### 권한
- ADMIN, USER

#### 응답 (200 OK)
```json
[
  {
    "id": 1,
    "name": "robot-1",
    "connected": true,
    "created_at": "2024-01-15T10:30:00Z",
    "server": {
      "host": "192.168.1.100",
      "port": 9001,
      "ping_endpoint": "/pang/ping"
    },
    "tracks": [
      {
        "type": "VIDEO",
        "name": "video_main",
        "endpoint": "/pang/ws/meb?channel=instant&name=token&source=base&track=video_main"
      },
      {
        "type": "LIDAR",
        "name": "lidar_front",
        "endpoint": "/pang/ws/meb?channel=instant&name=token&source=base&track=lidar_front"
      }
	],
    "actions": {
      "core": ["SLAM_NAVIGATION", "MAP_NAVIGATION"],
      "custom": []
    },
    "main_video_track_name": "video_main"
  }
]
```

### 4.2 특정 디바이스 조회

#### 엔드포인트
```
GET /devices/{deviceId}
```

#### 권한
- ADMIN, DEVICE, USER

#### 응답 (200 OK)
- 전체 디바이스 목록 조회의 응답과 동일

### 4.3 여러 디바이스 동시 조회

#### 내부 API (Java)
```java
List<DeviceResponse> findDevicesByIds(
  List<Long> deviceIds,
  AuthorizationType authorizationType
)
```

---

## 5. 디바이스 정보 수정

### 5.1 디바이스 이름 변경

#### 엔드포인트
```
PATCH /devices/{deviceId}
```

#### 권한
- ADMIN, USER

#### 요청 본문
```json
{
  "name": "new-robot-name"
}
```

#### 검증
- 새로운 이름이 중복되지 않아야 함

#### 응답 (204 No Content)

### 5.2 메인 비디오 트랙 변경

#### 엔드포인트
```
PATCH /devices/{deviceId}/main-video-track
```

#### 권한
- ADMIN, USER

#### 요청 본문
```json
{
  "name": "video_secondary"
}
```

#### 검증
- 지정된 트랙이 존재해야 함
- 트랙 타입이 VIDEO여야 함

#### 응답 (204 No Content)

#### 자동 폴백
```java
// 메인 트랙이 삭제되거나 존재하지 않는 경우
// 자동으로 VIDEO 타입의 첫 번째 트랙으로 변경
getMainVideoTrackName() {
  if (mainVideoTrackName != null &&
      tracks.hasTrack(VIDEO, mainVideoTrackName)) {
    return mainVideoTrackName;
  }
  return extractDefaultMainVideoTrackName(tracks);
}
```



---

## 6. 디바이스 삭제

#### 엔드포인트
```
DELETE /devices/{deviceId}
```

#### 권한
- ADMIN, USER

#### 처리 사항
- 데이터베이스에서 디바이스 레코드 완전 삭제

#### 응답 (204 No Content)

---

## 7. 디바이스 서버 정보

### 7.1 ServerInformation

```typescript
type ServerInformation = {
  host: string      // 서버 호스트 (예: 192.168.1.100)
  port: number      // 서버 포트 (예: 9001)
}
```

### 7.2 DeviceServerInformation

```typescript
type DeviceServerInformation = {
  host: string              // 디바이스 서버 호스트
  port: number              // 디바이스 서버 포트
  ping_endpoint: string     // 헬스 체크 엔드포인트 (예: /pang/ping)
}
```

#### 헬스 체크
- 엔드포인트: `GET {host}:{port}{ping_endpoint}`
- 목적: 디바이스 연결 상태 및 가용성 확인

---

## 8. 데이터베이스 스키마

### 8.1 devices 테이블

```sql
CREATE TABLE devices (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  token VARCHAR(255) NOT NULL UNIQUE,
  name VARCHAR(255) NOT NULL UNIQUE,
  connected BOOLEAN DEFAULT FALSE,
  tracks JSON,                    -- DeviceModule[] 저장
  actions JSON,                   -- DeviceAction 저장
  main_video_track_name VARCHAR(255),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

### 8.2 엔티티 관계

- **Device** (1) ←→ (N) **Track** (논리적 관계)
- **Device** (1) ←→ (1) **Actions** (포함 관계)

---

## 9. 에러 처리

### 9.1 등록 시 에러

| 에러 | 상태코드 | 원인 | 해결방법 |
|------|----------|------|---------|
| Secret Key 불일치 | 401/403 | `secretKey` 값이 잘못됨 | 올바른 secret key 확인 |
| 이름 중복 | 400 | 같은 이름의 디바이스 존재 | 다른 이름으로 변경 |

### 9.2 조회 시 에러

| 에러 | 상태코드 | 원인 | 해결방법 |
|------|----------|------|---------|
| 디바이스 없음 | 404 | 존재하지 않는 ID | 유효한 ID 확인 |
| 권한 없음 | 403 | 접근 권한 부족 | 관리자/사용자 권한 확인 |

### 9.3 수정 시 에러

| 에러 | 상태코드 | 원인 | 해결방법 |
|------|----------|------|---------|
| 메인 비디오 트랙 없음 | 400 | 지정된 트랙 미존재 | 유효한 트랙명 사용 |
| 이름 중복 | 400 | 새 이름이 중복됨 | 다른 이름으로 변경 |

---

## 10. 보안 고려사항

### 10.1 디바이스 인증

1. **등록 시**: Secret Key 기반 인증
   - 서버 설정의 `device.secretKey`와 비교
   - 네트워크 전송 시 TLS/HTTPS 권장

2. **통신 시**: 토큰 기반 인증
   - 각 디바이스에 고유 UUID 토큰 발급
   - WebSocket 연결 시 토큰 검증

### 10.2 권한 관리

```
Device 타입 권한:
├─ DEVICE: 자신의 디바이스만 접근 (상세 조회)
├─ ADMIN: 모든 디바이스 접근 (조회/수정/삭제)
└─ USER: 모든 디바이스 조회 (수정/삭제는 제한)
```

### 10.3 데이터 보안

- 민감 정보 (토큰)은 클라이언트에 노출되지 않음
- 데이터베이스 접근은 ORM (Spring Data JPA)을 통해 SQL injection 방지

---

## 11. 실제 사용 흐름 예시

### 11.1 새 로봇 등록 흐름

```
1. 로봇 부팅 및 초기화
2. POST /devices
   ├─ secretKey: "server-secret"
   ├─ name: "rescue-robot-1"
   ├─ tracks: [VIDEO, LIDAR, CONTROL, BATTERY, ...]
   └─ actions: {core: [SLAM_NAVIGATION, ...], custom: [...]}
3. 응답: {id: 1, token: "abc123...", name: "rescue-robot-1"}
4. 클라이언트 storeUpdateDeviceList() 호출
5. GET /devices → 전체 디바이스 목록 표시
```

### 11.2 디바이스 정보 조회 및 사용

```
1. GET /devices/{deviceId} → 디바이스 정보 조회
2. tracks 정보에서 필요한 모듈 선택
3. 각 모듈의 endpoint를 이용한 WebSocket 연결
4. VIDEO/LIDAR 모듈에서 센서 데이터 수신
```

### 11.3 메인 비디오 트랙 변경 흐름

```
1. 사용자가 비디오 트랙 선택
2. PATCH /devices/{deviceId}/main-video-track
   └─ name: "video_secondary"
3. 서버에서 트랙 유효성 확인
4. 클라이언트 editMainVideoTrack() → updateDeviceList()
5. 업데이트된 디바이스 목록 표시
```

---

## 12. 주요 제약사항

1. **이름 중복 불가**: 각 디바이스는 고유한 이름을 가져야 함
2. **토큰 변경 불가**: 등록 후 토큰은 수정할 수 없음
3. **메인 비디오 트랙 폴백**: 메인 트랙 삭제 시 자동으로 첫 번째 VIDEO 트랙 선택
4. **비동기 호출**: API 호출은 비동기이며, 캐싱 로직 활용

---

## 13. 관련 파일 목록

### 서버
- `api/src/main/java/kr/teamgrit/cobiz/api/device/` - 전체 디바이스 모듈
  - `domain/device/Device.java` - 엔티티
  - `domain/device/DeviceRepository.java` - 데이터 접근
  - `application/DeviceService.java` - 비즈니스 로직
  - `ui/DeviceController.java` - REST API
- `config.json` - PoC 기본 설정

### PoC HTML 관리 콘솔

- `ui/index.html` - 대시보드
- `ui/devices.html` - 디바이스 목록
- `ui/register.html` - 디바이스 등록
- `ui/device.html` - 디바이스 상세 및 수정
- `ui/settings.html` - 서버 설정 및 메타 정보

브라우저에서 바로 열려면 `ui/index.html`을 사용하면 됩니다.
