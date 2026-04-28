# Moth Integration 상태 보고

## 문제 식별

Heartbeat 메시지가 Moth 서버에는 발행되지만 Device Registry의 meb 구독자에게 도달하지 않는 현상.

## 근본 원인 분석

### 1단계: 엔드포인트 통일 ✓
- **문제**: 발행자 (`/pang/ws/pub`)와 구독자 (`/pang/ws/meb`)가 다른 엔드포인트 사용
- **해결책**: 모든 POC의 heartbeat publisher를 `/pang/ws/meb`으로 통일
- **상태**: 완료

### 2단계: 메시지 형식 수정 ✓
- **문제**: 발행 메시지가 `"topic"` 키 사용, Moth 프로토콜은 `"channel"` 키 요구
- **해결책**: 모든 publish 메시지를 `"topic"` → `"channel"`로 변경
- **상태**: 완료

### 3단계: route_mode 문제 해결 ✓
- **문제**: POC의 `route_mode`가 `"via_parent"`인 경우 heartbeat이 parent에만 전송되고 Moth에 발행되지 않음
- **해결책**: heartbeat은 항상 Moth에 발행하고, 추가로 parent에도 전송
- **상태**: 완료

## 현재 상태

### 변경 완료
1. `/pang/ws/pub` → `/pang/ws/meb` 엔드포인트 통일
2. `"topic"` → `"channel"` 키 변경
3. heartbeat 발행 로직 수정

### 테스트 결과
- **직접 테스트** (Python WebSocket): ✓ 작동
  - Moth meb 채널에서 pub/sub이 정상 작동
  - 와일드카드 채널명도 지원 확인
  
- **POC 통합 테스트**: ✗ 비작동
  - Heartbeat 메시지가 Moth로 도달하지 않음
  - 또는 subscri방에서 수신하지 못함

## 미해결 문제

### 가능한 원인들
1. **Heartbeat loop 미실행**: asyncio task가 제대로 시작되지 않음
2. **Moth 연결 실패**: WebSocket 연결 성공 후에도 메시지 전송 실패
3. **Moth 서버 이슈**: 특정 채널 조합에서 메시지 라우팅 실패
4. **타이밍 이슈**: subscription 이전에 publish가 일어남

### 디버깅 필요 항목
- [ ] heartbeat_loop이 실제로 실행되는지 로그 확인
- [ ] Moth 연결 후 메시지 전송 로그 확인
- [ ] Moth 서버의 채널 매핑 확인 (pub/sub 동작 검증)
- [ ] A2A 통신 검증 (Moth 대신 A2A로 heartbeat 전송 가능?)

## 다음 단계

1. **단기**: A2A 통신으로 heartbeat 전달 (Moth 우회)
2. **중기**: Moth 서버 로깅 분석
3. **장기**: Moth 서버 업그레이드 또는 대체 서비스 검토

## 참고
- Device Registry의 A2A 통신은 정상 작동
- 모든 POC 등록 및 command 전달 성공
- Moth의 기본 pub/sub은 작동 (직접 테스트 확인)
