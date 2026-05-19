# System Agent 구현 가이드

**문서 버전**: v0.1 (구현 기반)  
**최종 업데이트**: 2026-05-13  
**대상**: System Agent(RequestHandler, DeviceBridge, MissionPlanner 등) 개발자  
**목적**: 6개 System Agent의 구현 방법, 알고리즘, 패턴을 설명합니다.

> 💡 **이 문서는 구현 가이드입니다.** 역할 분할과 구조 개요는 [SYSTEM_AGENT_DESIGN.md](../SYSTEM_AGENT_DESIGN.md), 설계 원칙은 [principles.md](../core/principles.md)를 먼저 확인하세요.

---

## 1. 공통 패턴

### 1.1 BaseAgentRuntime 구현

모든 System Agent는 `BaseAgentRuntime`을 상속하여 다음을 구현합니다:

```python
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import asyncio
import logging
from datetime import datetime
from uuid import uuid4

logger = logging.getLogger(__name__)

class BaseAgentRuntime(ABC):
    """모든 System Agent의 기본 클래스"""
    
    def __init__(self, agent_id: str, agent_name: str, port: int):
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.port = port
        self.registry_client = RegistryClient()
        self.meb_client = MebClient()
        self.llm_client = LLMClient()
        
    async def start(self):
        """에이전트 시작"""
        logger.info(f"{self.agent_name} starting on port {self.port}")
        
        # 1. MEB 구독 시작 (이벤트 수신)
        await self.subscribe_to_meb()
        
        # 2. 에이전트별 초기화
        await self.initialize()
        
        # 3. HTTP 서버 시작
        await self.start_http_server()
        
        logger.info(f"{self.agent_name} started")
    
    @abstractmethod
    async def initialize(self):
        """에이전트별 초기화 로직"""
        pass
    
    async def subscribe_to_meb(self):
        """MEB 이벤트 구독"""
        await self.meb_client.subscribe(
            channel="agents",
            callback=self.on_event_received
        )
    
    async def on_event_received(self, event: Dict[str, Any]):
        """MEB 이벤트 수신 시 처리"""
        # 자신이 대상이 아니면 무시
        if self.agent_id not in event.get("target_agents", []):
            return
        
        # 에이전트별 이벤트 핸들러 호출
        await self.handle_event(event)
    
    @abstractmethod
    async def handle_event(self, event: Dict[str, Any]):
        """에이전트별 이벤트 처리 로직"""
        pass
    
    async def publish_event(self, event_type: str, data: Dict[str, Any],
                           target_agents: Optional[list] = None, severity: str = "INFO"):
        """MEB 이벤트 발행"""
        event = {
            "event_type": event_type,
            "actor_type": "SYSTEM",
            "actor_id": self.agent_id,
            "severity": severity,
            "target_agents": target_agents or [],
            "data": data,
            "created_at": datetime.utcnow().isoformat() + "Z"
        }
        
        await self.meb_client.publish(channel="agents", message=event)
    
    async def call_llm(self, prompt: str, temperature: float = 0.7, 
                      max_retries: int = 3) -> str:
        """LLM 호출 (Circuit Breaker + 재시도)"""
        
        for attempt in range(max_retries):
            try:
                response = await asyncio.wait_for(
                    self.llm_client.generate(
                        prompt=prompt,
                        temperature=temperature,
                        timeout=30
                    ),
                    timeout=35
                )
                return response
            except asyncio.TimeoutError:
                logger.warning(f"LLM timeout on attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
            except Exception as e:
                logger.error(f"LLM error: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
        
        raise Exception("LLM call failed after max retries")
    
    async def start_http_server(self):
        """HTTP 서버 시작 (FastAPI)"""
        # 구현은 각 에이전트에서
        pass
```

### 1.2 Event + AgentLog: 실행 기록 및 추적

**설계 원칙**:
- **Event**: "무엇이 일어났는가" - 주요 사건을 고수준으로 기록 (한 번만 발행)
- **AgentLog**: "어떻게 일어났는가" - Agent의 상세 실행 과정 기록 (입력, 출력, 판단, 소요 시간)
- **context_id**: 이 둘을 연결하는 흐름 ID (같은 사용자 명령, 같은 이상징후 등)

**모든 Agent의 _execute_role() 메서드는 다음 패턴을 따름**:

```python
async def _execute_role(self, parameters: dict[str, Any]) -> dict[str, Any]:
    from uuid import uuid4
    import time
    
    # 1. context_id 추출 또는 생성
    context_id = str(parameters.get("context_id") or f"ctx-{uuid4()}")
    start_time = time.time()
    
    # 2. SYS_REQUEST_RECEIVED 이벤트 (A2A 요청 수신 시)
    if request_id := parameters.get("request_id"):
        self.registry_client.ingest_event({
            "event_type": "SYS_REQUEST_RECEIVED",
            "context_id": context_id,  # ← 흐름 추적 ID
            "actor_type": "SYSTEM",
            "actor_id": self.state.agent_id,
            "target_type": "AGENT_COMMUNICATION",
            "target_id": request_id,
            "severity": "INFO",
            "data": {
                "request_id": request_id,
                "from_agent": "RequestHandler",
                "to_agent": self.__class__.__name__,
                "timestamp": utc_now()
            }
        })
    
    # 3. 메인 액션 실행 (시간 측정)
    try:
        action = str(parameters.get("action") or "default_action").strip()
        
        if action == "specific_action":
            # 액션 실행
            result = await self._perform_action(parameters)
            
            # AgentLog 기록 (성공)
            duration_ms = int((time.time() - start_time) * 1000)
            self.registry_client.ingest_agent_log({
                "context_id": context_id,  # ← Event와 같은 흐름 ID
                "agent_id": self.state.agent_id,
                "agent_role": "AGENT_NAME",  # REQUEST_HANDLER, MISSION_PLANNER 등
                "action": "specific_action",  # 실행한 구체적 작업
                "input": {
                    "param1": parameters.get("param1"),
                    "param2": parameters.get("param2"),
                },
                "output": result,
                "status": "SUCCESS",
                "duration_ms": duration_ms,
            })
        else:
            # 지원하지 않는 액션
            duration_ms = int((time.time() - start_time) * 1000)
            self.registry_client.ingest_agent_log({
                "context_id": context_id,
                "agent_id": self.state.agent_id,
                "agent_role": "AGENT_NAME",
                "action": "unsupported_action",
                "input": {"action": action},
                "output": {},
                "status": "FAILED",
                "duration_ms": duration_ms,
            })
            
            result = self._error_response("unsupported_action")
    
    except Exception as exc:
        # 액션 실행 중 오류
        duration_ms = int((time.time() - start_time) * 1000)
        self.registry_client.ingest_agent_log({
            "context_id": context_id,
            "agent_id": self.state.agent_id,
            "agent_role": "AGENT_NAME",
            "action": action,
            "input": {...},
            "output": {},
            "status": "FAILED",
            "duration_ms": duration_ms,
        })
        
        result = self._error_response(str(exc))
    
    # 4. SYS_RESPONSE_SENT 이벤트 (응답 전송 시)
    if request_id:
        self.registry_client.ingest_event({
            "event_type": "SYS_RESPONSE_SENT",
            "context_id": context_id,  # ← Event와 AgentLog를 연결
            "actor_type": "SYSTEM",
            "actor_id": self.state.agent_id,
            "target_type": "AGENT_COMMUNICATION",
            "target_id": request_id,
            "severity": "INFO" if result.get("status") == "ok" else "WARNING",
            "data": {
                "request_id": request_id,
                "from_agent": self.__class__.__name__,
                "to_agent": "RequestHandler",
                "response_status": result.get("status"),
                "timestamp": utc_now()
            }
        })
    
    return result
```

**context_id 흐름 예시**:

```
RequestHandler (사용자 명령 수신)
  └─ context_id = "ctx-abc-123" 생성
  ├─ Event: USER_COMMAND_RECEIVED (context_id: "ctx-abc-123")
  ├─ AgentLog: classify_intent (context_id: "ctx-abc-123")
  └─ MissionPlanner에 A2A 호출 (payload에 context_id 포함)
     └─ MissionPlanner 수신
        ├─ Event: SYS_REQUEST_RECEIVED (context_id: "ctx-abc-123")
        ├─ AgentLog: generate_proposals (context_id: "ctx-abc-123")
        └─ Event: SYS_RESPONSE_SENT (context_id: "ctx-abc-123")

사용자는 나중에 context_id "ctx-abc-123"으로 조회하면:
  - Event들: 전체 흐름의 주요 사건들
  - AgentLog들: 각 Agent의 상세 실행 과정 (판단 이유, 소요 시간 등)
```

### 1.3 LLM 호출 베스트 프랙티스

```python
class LLMCircuitBreaker:
    """LLM 호출 실패 시 Circuit Breaker 패턴"""
    
    def __init__(self, failure_threshold: int = 5, timeout_sec: int = 60):
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.timeout_sec = timeout_sec
        self.last_failure_time = None
        self.is_open = False
    
    async def call(self, llm_client, prompt: str) -> Optional[str]:
        """Circuit breaker를 통한 LLM 호출"""
        
        # Circuit이 열려있으면 실패 반환
        if self.is_open:
            if time.time() - self.last_failure_time < self.timeout_sec:
                logger.warning("Circuit breaker is OPEN. Falling back...")
                return None
            else:
                self.is_open = False
                self.failure_count = 0
        
        try:
            response = await llm_client.generate(prompt, timeout=30)
            self.failure_count = 0  # 성공 시 리셋
            return response
        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.failure_count >= self.failure_threshold:
                self.is_open = True
                logger.error(f"Circuit breaker OPEN after {self.failure_count} failures")
            
            raise
```

---

## 2. RequestHandler (포트 9116)

### 2.1 책임

- 사용자 자연어 명령을 Intent로 분류
- 해당 System Agent로 라우팅 또는 직접 처리
- USER_COMMAND_RECEIVED Event 발행 (context_id 포함)
- classify_intent AgentLog 기록
- 각 A2A 호출 시 context_id 전달 (흐름 추적)

### 2.2 Intent 분류 알고리즘

```python
class RequestHandler(BaseAgent):
    """사용자 요청 해석 및 라우팅"""
    
    INTENT_TYPES = {
        "QUERY": "데이터 조회 (현재 상태, 과거 데이터)",
        "MISSION": "미션/Task 할당 (새로운 작업)",
        "POLICY": "정책 관리 (Rule 생성/수정)",
        "EMERGENCY": "긴급 상황 (배터리 부족, 통신 단절)",
        "DIRECT": "직접 제어 (Device 즉시 조작)"
    }
    
    async def classify_intent(self, user_input: str) -> Dict[str, Any]:
        """
        사용자 입력을 Intent로 분류 (LLM 기반)
        
        Return:
            {
                "intent": "MISSION",
                "target_agent": "MissionPlanner",
                "parameters": {...}
            }
        """
        
        prompt = f"""사용자 명령을 다음 Intent 중 하나로 분류하고, 
해당 파라미터를 추출하세요.

Intent 정의:
- QUERY: 데이터 조회 (예: "현재 배터리 상태", "어제 미션 결과")
- MISSION: 새로운 미션 할당 (예: "기뢰탐지 해줘", "해역 조사 시작")
- POLICY: 정책 관리 (예: "배터리 30% 이하면 경고 규칙 만들어줘")
- EMERGENCY: 긴급 대응 (예: "USV-01 즉시 기지로 돌아와")
- DIRECT: 직접 제어 (예: "카메라 켜줘")

사용자 입력: "{user_input}"

응답 형식 (JSON):
{{
    "intent": "MISSION|QUERY|POLICY|EMERGENCY|DIRECT",
    "confidence": 0.95,
    "target_agent": "MissionPlanner|InsightReporter|PolicyManager|DeviceBridge|SystemSentinel",
    "parameters": {{...}}
}}
"""
        
        response = await self.call_llm(prompt, temperature=0.5)
        return json.loads(response)
    
    async def handle_query(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """데이터 조회 처리"""
        
        query_type = parameters.get("type")  # "battery", "mission_history", "device_status"
        
        if query_type == "battery":
            devices = await self.registry_client.get_all_devices()
            return {
                "devices": [
                    {
                        "device_id": d.device_id,
                        "battery_percent": d.battery_percent,
                        "status": d.status
                    }
                    for d in devices
                ]
            }
        
        elif query_type == "mission_history":
            mission_id = parameters.get("mission_id")
            mission = await self.registry_client.get_mission(mission_id)
            return {
                "mission": mission,
                "tasks": await self.registry_client.get_mission_tasks(mission_id)
            }
        
        # 기타 조회 로직...
        return {}
    
    async def route_to_agent(self, intent: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Intent에 따라 해당 Agent로 라우팅"""
        
        routing_map = {
            "MISSION": ("MissionPlanner", 9111),
            "POLICY": ("PolicyManager", 9112),
            "EMERGENCY": ("DeviceBridge", 9110),
            "DIRECT": ("DeviceBridge", 9110)
        }
        
        if intent not in routing_map:
            return {"error": f"Unknown intent: {intent}"}
        
        agent_name, agent_port = routing_map[intent]
        
        try:
            # 해당 Agent의 HTTP API 호출
            response = await self.call_agent_api(
                agent_name=agent_name,
                endpoint="/execute",
                payload=parameters,
                port=agent_port
            )
            return response
        except Exception as e:
            logger.error(f"Failed to route to {agent_name}: {e}")
            return {"error": str(e)}
    
    async def handle_event(self, event: Dict[str, Any]):
        """RequestHandler는 자신을 대상으로 하는 Event 거의 없음"""
        pass

### 2.3 Chat API 엔드포인트

```python
class UserRequest(BaseModel):
    """사용자 요청 데이터"""
    user_input: str

class ChatResponse(BaseModel):
    """Chat 응답 데이터"""
    type: str  # "RESPONSE" | "COMMAND"
    status: str  # "SUCCESS" | "PENDING" | "INFEASIBLE" | "ERROR"
    message: str
    data: Optional[Dict[str, Any]] = None

    command_id: Optional[str] = None
    intent_id: Optional[str] = None
    approval_id: Optional[str] = None
    reason_code: Optional[str] = None
    clarification_needed: Optional[bool] = None

@app.post("/request")
async def handle_user_request(self, request: UserRequest) -> ChatResponse:
    """
    사용자 자연어 요청 처리 (Chat Console용)
    
    【Request】
    POST /request
    {
        "user_input": "기뢰탐지 해줘"
    }
    
    【Response - QUERY 응답】
    {
        "type": "RESPONSE",
        "status": "SUCCESS",
        "message": "현재 배터리 상태입니다.",
        "data": {
            "devices": [
                {"device_id": "aauv-01", "battery_percent": 85, "status": "ONLINE"},
                {"device_id": "usv-01", "battery_percent": 72, "status": "ONLINE"}
            ]
        }
    }
    
    【Response - MISSION 응답 (Proposal 생성 시작)】
    {
        "type": "RESPONSE",
        "status": "PENDING",
        "message": "미션 계획 요청이 MissionPlanner로 전달됐습니다.",
        "intent_id": "intent-uuid-123"
    }
    
    【Response - EMERGENCY 응답】
    {
        "type": "COMMAND",
        "status": "SUCCESS",
        "message": "USV-01의 긴급 복귀 명령을 실행했습니다.",
        "command_id": "cmd-uuid-456"
    }
    
    【Response - 오류】
    {
        "type": "RESPONSE",
        "status": "INFEASIBLE",
        "message": "미션 수행 불가: 현재 미션을 수행할 수 있는 연결 장치가 없습니다.",
        "reason_code": "no_available_device",
        "clarification_needed": false
    }
    """
    
    try:
        # 1. Intent 분류
        intent_result = await self.classify_intent(request.user_input)
        intent = intent_result["intent"]
        
        # 2. QUERY: 직접 처리 → RESPONSE 응답
        if intent == "QUERY":
            query_result = await self.handle_query(intent_result["parameters"])
            return ChatResponse(
                type="RESPONSE",
                status="SUCCESS",
                message=f"조회 결과입니다.",
                data=query_result
            )
        
        # 3. MISSION: MissionPlanner로 라우팅 → Proposal 생성 시작 → PENDING 응답
        elif intent == "MISSION":
            proposal_result = await self.route_to_agent(
                "MISSION",
                intent_result["parameters"]
            )
            return ChatResponse(
                type="RESPONSE",
                status="PENDING",
                message="미션 계획 요청을 접수했습니다. Proposal 생성 후 승인 단계로 진행됩니다.",
                intent_id=proposal_result.get("intent_id")
            )
        
        # 4. EMERGENCY: DeviceBridge로 라우팅 → 긴급 명령 실행 → COMMAND 응답
        elif intent == "EMERGENCY":
            command_result = await self.route_to_agent(
                "EMERGENCY",
                intent_result["parameters"]
            )
            return ChatResponse(
                type="COMMAND",
                status="SUCCESS",
                message="긴급 명령을 실행했습니다.",
                command_id=command_result.get("command_id")
            )
        
        # 5. DIRECT: DeviceBridge로 라우팅 → 직접 제어
        elif intent == "DIRECT":
            direct_result = await self.route_to_agent(
                "DIRECT",
                intent_result["parameters"]
            )
            return ChatResponse(
                type="COMMAND",
                status="SUCCESS",
                message="명령을 실행했습니다.",
                command_id=direct_result.get("command_id")
            )
        
        # 6. POLICY: PolicyManager로 라우팅 → 정책 관리
        else:
            policy_result = await self.route_to_agent(
                "POLICY",
                intent_result["parameters"]
            )
            return ChatResponse(
                type="RESPONSE",
                status="SUCCESS",
                message="정책 변경이 완료되었습니다.",
                data=policy_result
            )
    
    except Exception as e:
        logger.error(f"Error handling user request: {e}")
        return ChatResponse(
            type="RESPONSE",
            status="ERROR",
            message=f"요청 처리 중 오류가 발생했습니다: {str(e)}"
        )
```

---

## 3. DeviceBridge (포트 9110)

### 3.1 책임

- Device Agent와의 A2A 통신 중개
- Task 할당 (MissionPlanner → Device Agent, context_id 포함)
- Device 상태 수신 (Heartbeat, Task Result, Problem Report)
- SYS_REQUEST_RECEIVED, SYS_RESPONSE_SENT Event 발행 (context_id 포함)
- relay_healthcheck, collect_result, dispatch_task AgentLog 기록
- Exponential Backoff 재시도

### 3.2 Task 전달 알고리즘

```python
class DeviceBridge(BaseAgent):
    """Device ↔ System 통신 게이트웨이"""
    
    def __init__(self):
        super().__init__("device-bridge", "DeviceBridge", 9110)
        self.device_endpoints = {}  # device_id → endpoint
        self.task_retry_state = {}  # task_id → retry_count
    
    async def assign_task(self, task: Dict[str, Any], target_device_id: str) -> Dict[str, Any]:
        """
        Device Agent에 Task 할당 (Exponential Backoff 재시도)
        """
        
        task_id = task["task_id"]
        max_retries = 5
        retry_delay = 1  # 초 단위
        
        for attempt in range(max_retries):
            try:
                # Device Agent의 endpoint 조회
                device = await self.registry_client.get_device(target_device_id)
                endpoint = device.agent_endpoint
                
                # A2A 프로토콜로 Task 전달
                response = await self.send_a2a_request(
                    endpoint=endpoint,
                    method="POST",
                    path="/task/assign",
                    payload={
                        "task_id": task_id,
                        "task": task,
                        "timeout_sec": task.get("timeout_sec", 300)
                    },
                    timeout=10
                )
                
                logger.info(f"Task {task_id} assigned to {target_device_id}")
                
                # Task 상태 업데이트
                await self.registry_client.update_task_status(
                    task_id=task_id,
                    status="ASSIGNED",
                    assigned_device_id=target_device_id
                )
                
                return {"success": True, "task_id": task_id}
            
            except Exception as e:
                logger.warning(f"Task assign attempt {attempt + 1} failed: {e}")
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 1.5  # Exponential backoff
                else:
                    # 모든 재시도 실패 → MissionPlanner에 알림
                    await self.publish_event(
                        event_type="SYS_TASK_ASSIGN_FAILED",
                        severity="ERROR",
                        target_agents=["MissionPlanner"],
                        data={
                            "task_id": task_id,
                            "target_device_id": target_device_id,
                            "reason": str(e)
                        }
                    )
                    return {"success": False, "error": str(e)}
        
        return {"success": False, "error": "Max retries exceeded"}
    
    async def collect_task_result(self, task_id: str, device_id: str) -> Dict[str, Any]:
        """Device Agent로부터 Task 결과 수집"""
        
        device = await self.registry_client.get_device(device_id)
        
        try:
            response = await self.send_a2a_request(
                endpoint=device.agent_endpoint,
                method="GET",
                path=f"/task/{task_id}/result",
                timeout=5
            )
            
            # Task 결과 저장
            await self.registry_client.update_task_result(
                task_id=task_id,
                result=response.get("result", {}),
                status=response.get("status", "COMPLETED")
            )
            
            return response
        except Exception as e:
            logger.error(f"Failed to collect result for task {task_id}: {e}")
            return None
    
    @app.post("/task/assign")
    async def assign_task_endpoint(self, request: TaskAssignRequest):
        """Task 할당 엔드포인트 (MissionPlanner → DeviceBridge)"""
        
        return await self.assign_task(
            task=request.task,
            target_device_id=request.target_device_id
        )
    
    async def handle_event(self, event: Dict[str, Any]):
        """MEB 이벤트 처리"""
        
        event_type = event["event_type"]
        
        if event_type == "SYS_TASK_DISPATCHED":
            # MissionPlanner가 Task를 dispatched로 표시
            await self.assign_task(
                task=event["data"]["task"],
                target_device_id=event["data"]["target_device_id"]
            )
        
        elif event_type == "DEVICE_TASK_RESULT":
            # Device Agent로부터 Task 결과
            await self.registry_client.update_task_result(
                task_id=event["data"]["task_id"],
                result=event["data"]["result"],
                status=event["data"]["status"]
            )
```

---

## 4. MissionPlanner (포트 9111)

### 4.1 책임

- 사용자 Intent → Proposal 생성 (LLM 기반, context_id 포함)
- Proposal → Mission 변환
- Mission 생명주기 관리 (READY → IN_PROGRESS → COMPLETED/FAILED)
- Task 분배 (DeviceBridge로 전달, context_id 포함)
- SYS_REQUEST_RECEIVED, SYS_RESPONSE_SENT Event 발행 (context_id 포함)
- generate_proposals AgentLog 기록 (LLM 판단 과정 포함)

### 4.2 Proposal 생성 알고리즘 (LLM 기반)

```python
class MissionPlanner(BaseAgent):
    """미션/Task 설계 및 생명주기 관리"""
    
    async def generate_proposal(self, user_intent: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        사용자 Intent → Proposal 자동 생성 (LLM)
        
        Device 능력 + 현재 상태를 LLM에게 제공
        """
        
        # 1. 현재 Device 상태 조회
        devices = await self.registry_client.get_all_devices()
        device_capabilities = [
            {
                "device_id": d.device_id,
                "type": d.type,  # USV, AUV, ROV
                "status": d.status,
                "battery_percent": d.battery_percent,
                "actions": d.actions,  # 수행 가능한 action 리스트
                "position": d.position
            }
            for d in devices
        ]
        
        # 2. LLM에게 Task 순서 생성 요청
        prompt = f"""사용자 명령에 따라 Task 순서를 생성하세요.
        
사용자 의도: {user_intent}
파라미터: {parameters}

현재 가용 Device:
{json.dumps(device_capabilities, indent=2)}

각 Device가 수행 가능한 Action:
- MOVE_TO: 특정 위치로 이동
- SCAN: 센서 스캔 (SONAR, CAMERA, WATER_QUALITY 등)
- SAMPLE: 샘플 수집
- HOLD_POSITION: 현재 위치 유지
- RETURN_TO_BASE: 기지로 복귀
- RECOVERY: 기뢰 등 회수

Task를 다음 순서대로 생성하세요:
1. Task 제목
2. required_action (위의 Action 중 하나)
3. target_device_id (가장 적합한 Device)
4. parameters (action별 파라미터)
5. timeout_sec (예상 소요 시간)

응답 형식 (JSON):
{{
    "tasks": [
        {{
            "title": "지점 A로 이동",
            "required_action": "MOVE_TO",
            "target_device_id": "aauv-01",
            "parameters": {{"location": "A", "depth": 100}},
            "timeout_sec": 600
        }},
        ...
    ],
    "estimated_duration_sec": 3600,
    "risk_level": "LOW|MEDIUM|HIGH"
}}
"""
        
        response = await self.call_llm(prompt, temperature=0.7)
        proposal_tasks = json.loads(response)
        
        # 3. Proposal 생성 및 저장
        proposal_id = str(uuid.uuid4())
        proposal = {
            "proposal_id": proposal_id,
            "source_intent": user_intent,
            "status": "PROPOSED",
            "tasks": proposal_tasks["tasks"],
            "estimated_duration_sec": proposal_tasks["estimated_duration_sec"],
            "risk_level": proposal_tasks["risk_level"],
            "created_at": datetime.utcnow().isoformat() + "Z"
        }
        
        await self.registry_client.create_proposal(proposal)
        
        return proposal
    
    async def approve_proposal(self, proposal_id: str) -> Dict[str, Any]:
        """
        Proposal 승인 → Mission 생성 및 실행
        """
        
        proposal = await self.registry_client.get_proposal(proposal_id)
        
        # 1. Proposal 상태 변경
        proposal["status"] = "APPROVED"
        await self.registry_client.update_proposal(proposal)
        
        # 2. Mission 생성
        mission_id = str(uuid.uuid4())
        mission = {
            "mission_id": mission_id,
            "source_proposal_id": proposal_id,
            "status": "READY",
            "tasks": proposal["tasks"],
            "created_at": datetime.utcnow().isoformat() + "Z",
            "started_at": None,
            "completed_at": None
        }
        
        await self.registry_client.create_mission(mission)
        
        # 3. Task 생성 및 분배
        tasks = []
        for idx, task_template in enumerate(proposal["tasks"]):
            task = {
                "task_id": str(uuid.uuid4()),
                "mission_id": mission_id,
                "source_proposal_task_idx": idx,
                "title": task_template["title"],
                "required_action": task_template["required_action"],
                "target_device_id": task_template["target_device_id"],
                "parameters": task_template["parameters"],
                "timeout_sec": task_template["timeout_sec"],
                "status": "PENDING",
                "sequence": idx,
                "created_at": datetime.utcnow().isoformat() + "Z"
            }
            tasks.append(task)
            await self.registry_client.create_task(task)
        
        # 4. Mission 상태 변경 및 첫 Task 할당
        mission["status"] = "IN_PROGRESS"
        mission["started_at"] = datetime.utcnow().isoformat() + "Z"
        await self.registry_client.update_mission(mission)
        
        # 첫 번째 Task를 DeviceBridge로 전달
        first_task = tasks[0]
        await self.publish_event(
            event_type="SYS_TASK_DISPATCHED",
            target_agents=["DeviceBridge"],
            data={
                "task": first_task,
                "target_device_id": first_task["target_device_id"]
            }
        )
        
        logger.info(f"Mission {mission_id} created and started")
        
        return {"mission_id": mission_id, "task_count": len(tasks)}
    
    async def on_task_completed(self, task_id: str, mission_id: str):
        """Task 완료 시 다음 Task 실행"""
        
        mission = await self.registry_client.get_mission(mission_id)
        tasks = await self.registry_client.get_mission_tasks(mission_id)
        
        completed_task = await self.registry_client.get_task(task_id)
        current_sequence = completed_task["sequence"]
        
        # 다음 Task 찾기
        next_task = None
        for task in tasks:
            if task["sequence"] == current_sequence + 1:
                next_task = task
                break
        
        if next_task:
            # 다음 Task 할당
            await self.publish_event(
                event_type="SYS_TASK_DISPATCHED",
                target_agents=["DeviceBridge"],
                data={
                    "task": next_task,
                    "target_device_id": next_task["target_device_id"]
                }
            )
        else:
            # 모든 Task 완료 → Mission 완료
            mission["status"] = "COMPLETED"
            mission["completed_at"] = datetime.utcnow().isoformat() + "Z"
            await self.registry_client.update_mission(mission)
            
            # InsightReporter에 리포트 생성 요청
            await self.publish_event(
                event_type="SYS_MISSION_COMPLETED",
                target_agents=["InsightReporter"],
                data={"mission_id": mission_id}
            )
    
    async def handle_event(self, event: Dict[str, Any]):
        """MEB 이벤트 처리"""
        
        event_type = event["event_type"]
        
        if event_type == "SYS_TASK_COMPLETED":
            await self.on_task_completed(
                task_id=event["data"]["task_id"],
                mission_id=event["data"]["mission_id"]
            )
        
        elif event_type == "SYS_TASK_FAILED":
            # Task 실패 처리
            mission_id = event["data"]["mission_id"]
            mission = await self.registry_client.get_mission(mission_id)
            mission["status"] = "FAILED"
            mission["failed_reason"] = event["data"]["reason"]
            await self.registry_client.update_mission(mission)
```

---

## 5. PolicyManager (포트 9112)

### 5.1 책임

- Policy/Rule 관리 (CRUD)
- Event 감시 → Rule 평가 → 자동 실행 (auto_execute=true)
- SYS_REQUEST_RECEIVED, SYS_RESPONSE_SENT Event 발행 (context_id 포함)
- evaluate_policies AgentLog 기록 (정책 매칭 과정, 의사결정 이유)
- **RuleEngine을 사용하여 조건 평가 및 액션 실행**

### 5.2 PolicyManager의 구조

```python
from rule_engine import RuleEngine

class PolicyManager(BaseAgent):
    """정책 기반 자동 대응 (RuleEngine 래퍼)"""
    
    def __init__(self):
        super().__init__("policy-manager", "PolicyManager", 9112)
        self.rule_engine = RuleEngine()  # 저수준 Rule 처리 엔진
    
    async def initialize(self):
        """PolicyManager 초기화"""
        # 모든 활성 Rule을 RuleEngine에 등록
        rules = await self.registry_client.get_all_rules()
        for rule in rules:
            if rule.get("enabled", True):
                self.rule_engine.add_rule(rule)
```

### 5.3 Policy 매칭 & Rule 실행

```python
class PolicyManager(BaseAgent):
    """정책 기반 자동 대응"""
    
    async def handle_event(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Event 수신 → RuleEngine으로 Rule 평가 → 자동 실행
        """
        
        # 1. RuleEngine에 Event 처리 위임
        results = await self.rule_engine.process_event(event)
        
        # 2. Rule 실행 결과 처리
        executed = []
        for result in results:
            if result["status"] == "executed":
                executed.append(result)
                
                # 3. 필요하면 추가 작업 (예: 알림 발송, 로깅)
                await self._post_execute_handler(result, event)
        
        return executed
    
    async def _post_execute_handler(self, result: Dict[str, Any], event: Dict[str, Any]):
        """Rule 실행 후 추가 처리"""
        
        action_type = result.get("action")
        
        if action_type == "ALERT":
            # Alert 기록
            await self.registry_client.create_alert({
                "rule_id": result["rule_id"],
                "message": result.get("message"),
                "severity": result.get("severity", "INFO"),
                "triggered_by": event["event_type"]
            })
        
        elif action_type == "AUTO_TASK":
            # AUTO_TASK는 RuleEngine이 이미 생성했음
            # 여기서는 추적/로깅만 수행
            logger.info(f"Auto task created by rule {result['rule_id']}")
    
    async def match_and_execute_policy(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        🔄 (Deprecated) 기존 이름 유지 (하위 호환성)
        실제 구현은 handle_event()를 사용
        """
        return await self.handle_event(event)
    
    def _matches_trigger(self, policy: Dict[str, Any], event: Dict[str, Any]) -> bool:
        """Policy 트리거 조건 매칭"""
        
        trigger = policy.get("trigger", {})
        event_type = trigger.get("event_type")
        
        # Event type 매칭
        if event_type and event["event_type"] != event_type:
            return False
        
        # 추가 조건 매칭 (device_type, severity 등)
        for key, expected_value in trigger.items():
            if key == "event_type":
                continue
            
            actual_value = event["data"].get(key)
            if actual_value != expected_value:
                return False
        
        return True
    
    async def _execute_policy(self, policy: Dict[str, Any], event: Dict[str, Any]) -> Dict[str, Any]:
        """Policy 실행"""
        
        action = policy.get("action", {})
        action_type = action.get("type")
        
        if action_type == "ALERT":
            # Alert 발행
            await self.publish_event(
                event_type="SYS_ALERT",
                severity=action.get("severity", "WARNING"),
                data={
                    "policy_id": policy["policy_id"],
                    "message": action.get("message"),
                    "triggered_by": event["event_type"]
                }
            )
            return {"policy_id": policy["policy_id"], "action": "ALERT", "status": "executed"}
        
        elif action_type == "AUTO_TASK":
            # 자동 Task 할당
            task = {
                "task_id": str(uuid.uuid4()),
                "title": action.get("task_title", "Auto-generated task"),
                "required_action": action.get("required_action"),
                "target_device_id": await self._select_device(action.get("device_filter")),
                "parameters": action.get("parameters", {}),
                "timeout_sec": action.get("timeout_sec", 300),
                "status": "PENDING"
            }
            
            # Mission 생성 후 Task 할당
            mission_id = str(uuid.uuid4())
            # ... Mission 생성 로직 ...
            
            return {"policy_id": policy["policy_id"], "action": "AUTO_TASK", "task_id": task["task_id"]}
        
        elif action_type == "DEVICE_STATE_CHANGE":
            # Device 상태 변경
            device_id = action.get("device_id")
            new_status = action.get("status")
            
            await self.registry_client.update_device_status(
                device_id=device_id,
                status=new_status
            )
            
            return {"policy_id": policy["policy_id"], "action": "DEVICE_STATE_CHANGE", "status": "executed"}
        
        return {"policy_id": policy["policy_id"], "action": "UNKNOWN", "status": "failed"}
    
    async def handle_event(self, event: Dict[str, Any]):
        """MEB 이벤트 처리"""
        
        # Policy 매칭 및 자동 실행
        await self.match_and_execute_policy(event)
```

---

## 6. SystemSentinel (포트 9113)

### 6.1 책임

- Device 건전성 감시 (Heartbeat 타임아웃, 배터리, 센서 이상)
- SYS_REQUEST_RECEIVED, SYS_RESPONSE_SENT Event 발행 (context_id 포함)
- SYS_ANOMALY_DETECTED Event 발행 (이상징후 감지 시)
- detect_anomalies AgentLog 기록 (감지 내용, 심각도, 이상 유형)
- AgentConnection 자동 관리 (3단계 필터링)
- Alert 생성

### 6.2 Heartbeat 타임아웃 감시

```python
class SystemSentinel(BaseAgent):
    """시스템 건전성 감시"""
    
    def __init__(self):
        super().__init__("system-sentinel", "SystemSentinel", 9113)
        self.device_heartbeat_timestamps = {}  # device_id → last_heartbeat_time
        self.HEARTBEAT_TIMEOUT_SEC = 10
        self.BATTERY_WARNING_PERCENT = 30
        self.BATTERY_CRITICAL_PERCENT = 10
    
    async def monitor_heartbeats(self):
        """주기적으로 Device Heartbeat 감시"""
        
        while True:
            try:
                devices = await self.registry_client.get_all_devices()
                
                for device in devices:
                    if device.status != "ONLINE":
                        continue
                    
                    last_heartbeat = self.device_heartbeat_timestamps.get(device.device_id)
                    if not last_heartbeat:
                        continue
                    
                    time_since_last = time.time() - last_heartbeat
                    
                    if time_since_last > self.HEARTBEAT_TIMEOUT_SEC:
                        # Heartbeat 타임아웃 처리
                        await self._handle_heartbeat_timeout(device)
                
                await asyncio.sleep(1)  # 1초마다 체크
            
            except Exception as e:
                logger.error(f"Error in monitor_heartbeats: {e}")
                await asyncio.sleep(5)
    
    async def _handle_heartbeat_timeout(self, device: Dict[str, Any]):
        """Heartbeat 타임아웃 처리"""
        
        device_id = device["device_id"]
        logger.warning(f"Device {device_id} heartbeat timeout")
        
        # Device 상태 변경
        await self.registry_client.update_device_status(
            device_id=device_id,
            status="OFFLINE"
        )
        
        # Alert 발행
        await self.publish_event(
            event_type="SYS_DEVICE_HEARTBEAT_TIMEOUT",
            severity="WARNING",
            target_agents=["PolicyManager"],
            data={
                "device_id": device_id,
                "timeout_sec": self.HEARTBEAT_TIMEOUT_SEC
            }
        )
    
    async def monitor_battery(self, heartbeat_event: Dict[str, Any]):
        """배터리 상태 감시"""
        
        device_id = heartbeat_event["actor_id"]
        battery_percent = heartbeat_event["data"]["battery_percent"]
        
        if battery_percent <= self.BATTERY_CRITICAL_PERCENT:
            severity = "CRITICAL"
            level = "CRITICAL"
        elif battery_percent <= self.BATTERY_WARNING_PERCENT:
            severity = "WARNING"
            level = "WARNING"
        else:
            return  # 정상 범위
        
        await self.publish_event(
            event_type="SYS_DEVICE_BATTERY_LOW",
            severity=severity,
            target_agents=["PolicyManager"],
            data={
                "device_id": device_id,
                "battery_percent": battery_percent,
                "level": level
            }
        )
    
    async def handle_event(self, event: Dict[str, Any]):
        """MEB 이벤트 처리"""
        
        event_type = event["event_type"]
        
        if event_type == "DEVICE_HEALTHCHECK":
            # Heartbeat 수신 시 타임스탐프 갱신
            device_id = event["actor_id"]
            self.device_heartbeat_timestamps[device_id] = time.time()
            
            # 배터리 체크
            await self.monitor_battery(event)
        
        elif event_type == "SYS_DEVICE_SENSOR_ANOMALY":
            # 센서 이상 감시
            await self.publish_event(
                event_type="SYS_ALERT",
                severity="WARNING",
                target_agents=["PolicyManager"],
                data=event["data"]
            )
```

---

## 7. InsightReporter (포트 9114)

### 7.1 책임

- Mission 리포트 자동 생성 (Mission 완료 시, context_id 포함)
- 사용자 요청 시 리포트 생성 (범위 지정, context_id 포함)
- SYS_REQUEST_RECEIVED, SYS_RESPONSE_SENT Event 발행 (context_id 포함)
- generate_report AgentLog 기록 (리포트 생성 과정, 통계)
- JSON 형식 리포트

### 7.2 리포트 생성

```python
class InsightReporter(BaseAgent):
    """데이터 조회 & 분석 리포트 생성"""
    
    async def generate_mission_report(self, mission_id: str) -> Dict[str, Any]:
        """
        Mission 완료 시 자동 리포트 생성
        """
        
        # 1. Mission 및 Task 데이터 조회
        mission = await self.registry_client.get_mission(mission_id)
        tasks = await self.registry_client.get_mission_tasks(mission_id)
        
        # 2. 통계 계산
        total_duration = 0
        completed_tasks = 0
        failed_tasks = 0
        
        for task in tasks:
            if task["status"] == "COMPLETED":
                completed_tasks += 1
                total_duration += task.get("duration_sec", 0)
            elif task["status"] == "FAILED":
                failed_tasks += 1
        
        # 3. 리포트 생성
        report = {
            "report_id": str(uuid.uuid4()),
            "type": "MISSION_REPORT",
            "mission_id": mission_id,
            "title": f"Mission Report - {mission_id}",
            "summary": {
                "mission_status": mission["status"],
                "total_duration_sec": total_duration,
                "completed_tasks": completed_tasks,
                "failed_tasks": failed_tasks,
                "success_rate": completed_tasks / len(tasks) if tasks else 0
            },
            "details": {
                "tasks": [
                    {
                        "task_id": t["task_id"],
                        "title": t["title"],
                        "status": t["status"],
                        "required_action": t["required_action"],
                        "assigned_device_id": t.get("assigned_device_id"),
                        "duration_sec": t.get("duration_sec"),
                        "result": t.get("result", {})
                    }
                    for t in tasks
                ],
                "mission_metadata": {
                    "created_at": mission["created_at"],
                    "started_at": mission.get("started_at"),
                    "completed_at": mission.get("completed_at")
                }
            },
            "created_at": datetime.utcnow().isoformat() + "Z"
        }
        
        # 4. 리포트 저장
        await self.registry_client.create_report(report)
        
        return report
    
    async def generate_custom_report(self, request: CustomReportRequest) -> Dict[str, Any]:
        """
        사용자 요청 시 커스텀 리포트 생성
        
        POST /report/generate
        {
            "type": "DEVICE_STATUS",
            "filters": {
                "device_ids": ["aauv-01"],
                "start_time": "2026-05-01T00:00:00Z",
                "end_time": "2026-05-13T23:59:59Z"
            }
        }
        """
        
        report_type = request.type  # DEVICE_STATUS, MISSION_HISTORY, BATTERY_TREND
        
        if report_type == "DEVICE_STATUS":
            devices = await self.registry_client.get_devices(
                device_ids=request.filters.get("device_ids")
            )
            
            report = {
                "report_id": str(uuid.uuid4()),
                "type": "DEVICE_STATUS",
                "devices": [
                    {
                        "device_id": d.device_id,
                        "status": d.status,
                        "battery_percent": d.battery_percent,
                        "position": d.position,
                        "last_heartbeat": d.last_heartbeat_at
                    }
                    for d in devices
                ],
                "generated_at": datetime.utcnow().isoformat() + "Z"
            }
        
        return report
    
    async def handle_event(self, event: Dict[str, Any]):
        """MEB 이벤트 처리"""
        
        event_type = event["event_type"]
        
        if event_type == "SYS_MISSION_COMPLETED":
            # Mission 완료 시 자동 리포트 생성
            mission_id = event["data"]["mission_id"]
            await self.generate_mission_report(mission_id)
```

---

## 8. 참고자료

- [A2A Protocol](../core/a2a-protocol.md) - Agent 간 통신
- [Event Types](../core/event-types.md) - 13개 MEB 이벤트
- [SYSTEM_AGENT_DESIGN.md](../SYSTEM_AGENT_DESIGN.md) - 아키텍처 개요
- [principles.md](../core/principles.md) - 설계 원칙
