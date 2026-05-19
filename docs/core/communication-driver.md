# 디바이스 통신 드라이버 전략

**문서 버전**: 1.0  
**목적**: Device 간 물리적 데이터 전송을 담당하는 드라이버 선택 및 multi-hop relay 알고리즘 정의

---

## 1. 개요

### 1.1 정의

**Communication Driver**: Device ↔ Device 간 물리적 데이터 전송을 담당하는 모듈

```
Application Layer (A2A 메시지)
        ↓
Network Routing (AgentConnection 기반 경로 결정)
        ↓
Driver Selection (primary_medium 기반)
        ↓
Communication Driver (RF, Acoustic, Wired 등)
        ↓
Physical Layer (실제 송수신)
```

### 1.2 역할

- **동적 드라이버 선택**: AgentConnection의 primary_medium에서 선택
- **multi-hop 지원**: Device-Device-System Agent 계층 구조 relay
- **환경 적응**: 수중/수상 환경에 맞게 매체 자동 전환
- **시뮬레이션 지원**: 실제 HW 없이 동작 테스트 가능

---

## 2. 네트워크 유형별 드라이버 스펙

### 2.0 기본 인터페이스

```python
from abc import ABC, abstractmethod

class CommunicationDriver(ABC):
    """모든 드라이버가 구현해야 하는 기본 인터페이스"""
    
    async def send(self, target_device_id: str, message: bytes) -> bool:
        """
        메시지 송신
        
        Args:
            target_device_id: 수신자 Device ID
            message: 송신할 바이트 메시지
        
        Returns:
            성공 여부 (True: 성공, False: 실패)
        """
        raise NotImplementedError
```

### 2.1 Wired (유선, 최고 우선순위)

**특성**: 물리 케이블을 통한 통신

```python
class WiredDriver(CommunicationDriver):
    SPECS = {
        "range": "0.5-100m (케이블 길이)",
        "bandwidth": "1-10 Mbps",
        "latency": "5-20 ms",
        "power_consumption": "0.1-0.5 W",
        "packet_loss": "0.0-0.1%",
        "reliability": "very_high"
    }
    # 구현은 구현 단계에서 (Section 5의 MockDriver 패턴 참고)
```

**사용 사례**: ROV ↔ USV (톱날 케이블 연결)

### 2.2 RF (Radio Frequency, 2순위)

**특성**: 수상 또는 근거리 공중 통신

```python
class RFDriver(CommunicationDriver):
    SPECS = {
        "frequency": "2.4 GHz ISM band",
        "range": "1-10 km (LOS)",
        "bandwidth": "250 kbps",
        "latency": "50-200 ms",
        "power_consumption": "1-2 W",
        "packet_loss": "1-5% (normal), 10-20% (edge)",
        "reliability": "medium"
    }
    # 구현은 구현 단계에서
```

**사용 사례**: USV ↔ System Agent (수상)

### 2.3 Acoustic (음파, 3순위)

**특성**: 수중 음파 통신

```python
class AcousticDriver(CommunicationDriver):
    SPECS = {
        "frequency": "10-200 kHz",
        "range": "100-5000m (수질에 따라)",
        "bandwidth": "1-10 kbps",
        "latency": "100-500 ms (거리 의존)",
        "power_consumption": "5-20 W",
        "packet_loss": "5-20%",
        "reliability": "medium_low"
    }
    # 구현은 구현 단계에서
```

**사용 사례**: AUV ↔ USV (수중 ↔ 수상)

### 2.4 위성 통신 (4순위)

**특성**: 위성 통신 (Long range, 저대역폭)

```python
class SatelliteDriver(CommunicationDriver):
    SPECS = {
        "range": "전 지구",
        "bandwidth": "1-10 kbps",
        "latency": "500-2000 ms",
        "power_consumption": "5-50 W",
        "packet_loss": "1-5%",
        "reliability": "medium"
    }
    # 구현은 구현 단계에서
```

### 2.5 관성 항법 (최저 우선순위)

**특성**: GPS 없이 장치 내부 센서(가속도, 자이로)로 위치 추정

```python
class InertialDriver(CommunicationDriver):
    SPECS = {
        "range": "local_only",
        "bandwidth": "N/A (위치 추정)",
        "latency": "N/A",
        "power_consumption": "0.1-0.5 W",
        "reliability": "low (오차 누적)"
    }
    # 구현은 구현 단계에서
```

---

## 3. 드라이버 선택 알고리즘

### 3.1 AgentConnection 기반 선택

```python
class DeviceAgent:
    async def select_driver(self, target_device_id: str) -> CommunicationDriver:
        """target_device_id로 전송할 최적 드라이버 선택"""
        
        # 1. AgentConnection 조회 (로컬 캐시에서)
        conn = self.local_connections_cache.get(
            f"{self.device_id}-{target_device_id}"
        )
        
        if not conn or conn.deleted_at is not None:
            raise ConnectionError(f"No active connection to {target_device_id}")
        
        # 2. primary_medium 기반으로 드라이버 선택
        primary_medium = conn.primary_medium
        driver_class = self.DRIVERS[primary_medium]
        
        # 3. 드라이버 인스턴스 생성
        driver = driver_class(config=self.config.drivers[primary_medium])
        
        return driver
    
    DRIVERS = {
        "WIRED": WiredDriver,
        "RF": RFDriver,
        "ACOUSTIC": AcousticDriver,
        "SATELLITE": SatelliteDriver,
        "INERTIAL": InertialDriver
    }
```

### 3.2 폴백 전략

primary 드라이버 실패 시 대체 드라이버 시도:

```python
async def send_with_fallback(self, target_device_id: str, 
                              message: bytes) -> bool:
    """primary 드라이버 실패 시 대체 드라이버 시도"""
    
    conn = self.local_connections_cache.get(
        f"{self.device_id}-{target_device_id}"
    )
    
    # 우선순위: primary → active_mediums 순서
    mediums_to_try = [conn.primary_medium] + \
                     [m for m in conn.active_mediums 
                      if m != conn.primary_medium]
    
    for medium in mediums_to_try:
        try:
            driver = self.DRIVERS[medium](self.config)
            success = await driver.send(target_device_id, message)
            
            if success:
                logger.info(f"Sent via {medium}")
                return True
        except Exception as e:
            logger.warning(f"Failed with {medium}: {e}")
            continue
    
    raise CommunicationError(f"All drivers failed for {target_device_id}")
```

---

## 4. 다중 홉 릴레이

### 4.1 계층 구조 예시

```
System Agent (육상)
    ↓ (RF 또는 위성)
Topside Computer
    ↓ (Ethernet over Fiber)
USV (수상 중개)
    ↓ (Acoustic)
ROV (수중 작업)
```

### 4.2 경로 결정 (BFS)

SystemSentinel이 AgentConnection을 기반으로 BFS로 경로 계산:

```python
async def find_relay_path(source_device_id: str, 
                          target_device_id: str) -> list[str]:
    """source → target으로의 최단 경로 찾기 (BFS)"""
    
    # 모든 활성 AgentConnection 조회 (deleted_at IS NULL)
    connections = await self.registry.get_all_agent_connections()
    
    # 인접 리스트 구성
    graph = {}
    for conn in connections:
        if conn.deleted_at is None:
            if conn.source_device_id not in graph:
                graph[conn.source_device_id] = []
            graph[conn.source_device_id].append(conn.target_device_id)
    
    # BFS로 최단 경로 찾기
    from collections import deque
    queue = deque([(source_device_id, [source_device_id])])
    visited = {source_device_id}
    
    while queue:
        current, path = queue.popleft()
        
        if current == target_device_id:
            return path
        
        for neighbor in graph.get(current, []):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, path + [neighbor]))
    
    return []  # 경로 없음
```

### 4.3 Relay 메시지 전달

Device가 자신 목적지가 아닌 메시지를 수신하면 다음 hop으로 relay:

```python
class DeviceAgent:
    async def on_relay_message(self, source_device_id: str, 
                               target_device_id: str, 
                               message: bytes):
        """다른 Device로부터 relay 메시지 수신"""
        
        if target_device_id == self.device_id:
            # 이 Device가 최종 목적지
            await self.process_message(message)
        else:
            # 다른 Device로 relay
            await self.relay_message(target_device_id, message)
    
    async def relay_message(self, target_device_id: str, 
                           message: bytes):
        """메시지를 다음 hop으로 전달"""
        
        # 경로 결정 (System Sentinel이 계산한 경로 사용)
        relay_path = await self.get_relay_path_from_cache(target_device_id)
        
        if not relay_path or len(relay_path) < 2:
            logger.error(f"No relay path to {target_device_id}")
            return
        
        # 다음 hop의 endpoint 조회
        next_hop_device_id = relay_path[1]
        next_hop_endpoint = await self.registry.get_device_endpoint(next_hop_device_id)
        
        # A2A로 전달
        driver = await self.select_driver(next_hop_device_id)
        success = await driver.send(next_hop_endpoint, message)
        
        if success:
            logger.info(f"Relayed message to {next_hop_device_id}")
```

---

## 5. 시뮬레이션 환경

### 5.1 MockDriver 구현 (✅ 완전한 구현 예시)

```python
class MockDriver(CommunicationDriver):
    """
    시뮬레이션 환경에서 물리 통신 모의
    
    ⚠️ 이 클래스는 다른 드라이버(Wired, RF, Acoustic 등)의 구현 참고용
    완전한 구현 예시입니다.
    """
    
    def __init__(self, latency_ms: int = 100, 
                 packet_loss_percent: float = 2.0):
        self.latency_ms = latency_ms
        self.packet_loss_percent = packet_loss_percent
    
    async def send(self, target_agent_id: str, 
                   message: bytes) -> bool:
        """메시지를 메모리에 저장 (실제 송신 아님)"""
        import random
        
        # 패킷 손실 시뮬레이션
        if random.random() * 100 < self.packet_loss_percent:
            logger.warning(f"Packet loss to {target_agent_id}")
            return False
        
        # 지연 시뮬레이션
        await asyncio.sleep(self.latency_ms / 1000.0)
        
        logger.info(f"[MOCK] Sent {len(message)}B to {target_agent_id}")
        return True
```

### 5.2 Device 설정

```yaml
# device/configs/communication.yaml

devices:
  - device_id: "USV-01"
    agent_port: 9201
    environment_state: "SURFACE"
    available_mediums: ["RF", "Satellite", "Acoustic"]
    driver:
      type: "mock"  # 또는 "real"
      latency_ms: 150
      packet_loss_percent: 2.0
  
  - device_id: "AUV-01"
    agent_port: 9202
    environment_state: "UNDERWATER"
    available_mediums: ["Acoustic", "Inertial"]
    driver:
      type: "mock"
      latency_ms: 300
      packet_loss_percent: 5.0
  
  - device_id: "ROV-01"
    agent_port: 9203
    environment_state: "UNDERWATER"
    available_mediums: ["Wired", "Acoustic"]
    gateway_agent_id: "USV-01"
    driver:
      type: "mock"
      latency_ms: 10  # Wired는 빠름
      packet_loss_percent: 0.0
```

---

## 6. 매체 우선순위

| 순위 | 매체 | 우선도 | 특징 |
|------|------|--------|------|
| 1️⃣ | Wired | 1 | 최고 신뢰성, 고대역폭 |
| 2️⃣ | RF | 2 | 수상 통신, 중간 거리 |
| 3️⃣ | Acoustic | 3 | 수중 통신, 저대역폭 |
| 4️⃣ | Satellite | 4 | 전 지구, 고지연 |
| 5️⃣ | Inertial | 5 | 최후의 수단, 오차 누적 |

---

**관련 문서**:
- [AgentConnection](agent-connection.md)
- [A2A Protocol](a2a-protocol.md)
- [Event Types](event-types.md)
- [System Architecture](../SYSTEM_ARCHITECTURE.md)
