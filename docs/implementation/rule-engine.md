# Rule Engine 구현 가이드

**문서 버전**: v0.1  
**최종 업데이트**: 2026-05-13  
**대상**: Rule Engine, PolicyManager 개발자  
**목적**: Event 기반 자동화 규칙의 설계, 평가, 실행 로직

> 💡 **이 문서는 Rule Engine 구현을 위한 기술 가이드입니다.** 정책 관리는 [system-agent.md](./system-agent.md#5-policymanager)를 참고하세요.

---

## 1. Rule Engine 개요

### 1.1 정의

**Rule**: Event 수신 → 조건 평가 → 자동 액션 실행

```
Event 발생
  ↓
Rule Engine이 등록된 모든 Rule을 평가
  ↓
조건 일치하는 Rule 찾기
  ↓
매칭된 Rule을 Priority 순서대로 실행
```

### 1.2 용어

| 용어 | 정의 | 예시 |
|------|------|------|
| **Rule** | Event에 반응하는 자동화 규칙 | "배터리 < 10% → RETURN_TO_BASE" |
| **Condition** | Rule이 실행되는 조건 | `device.battery < 10 AND device.status = "ONLINE"` |
| **Action** | 조건 일치 시 실행할 동작 | ALERT, AUTO_TASK, DEVICE_STATE_CHANGE |
| **Trigger** | Rule을 발동하는 Event 타입 | DEVICE_HEALTHCHECK, SYS_ALERT |
| **Priority** | 여러 Rule이 매칭될 때 실행 순서 | 1(높음) ~ 100(낮음) |

---

## 2. Rule 조건 표현식 (SQL WHERE 스타일)

### 2.1 문법

```
condition := expr [ AND | OR ] expr
expr := operand operator value
operand := device.* | task.* | system.*
operator := ==, !=, <, >, <=, >=, IN, BETWEEN, LIKE
value := string | number | list
```

### 2.2 데이터 대상

#### Device 상태
```python
device.device_id       # "aauv-01" (string)
device.type            # "USV|AUV|ROV" (string)
device.status          # "ONLINE|OFFLINE|DEGRADED|REMOVED" (string)
device.battery_percent # 0-100 (number)
device.signal_strength # 0-100 (number)
device.depth           # 미터 (number)
device.position        # {"lat": 37.55, "lon": 126.99} (object)
device.environment_state # "SURFACE|UNDERWATER" (string)
```

#### Task 상태
```python
task.task_id           # Task UUID (string)
task.status            # "PENDING|ASSIGNED|IN_PROGRESS|COMPLETED|FAILED|ABORTED" (string)
task.type              # "DEVICE_TASK|SYSTEM_TASK|REPORT_TASK" (string)
task.required_action   # "MOVE_TO|SCAN|RETURN_TO_BASE|HOLD_POSITION" (string)
task.assigned_device_id # Device ID (string)
task.duration_sec      # 초 단위 (number)
task.timeout_sec       # 타임아웃 (number)
```

#### System 상태
```python
system.time            # 현재 시간 (ISO8601)
system.mode            # "NORMAL|EMERGENCY|MAINTENANCE" (string)
system.active_devices_count # (number)
```

### 2.3 조건 예시

```python
# 예시 1: 단일 조건
"device.battery < 30"

# 예시 2: 복합 조건 (AND)
"device.battery < 30 AND device.status = 'ONLINE'"

# 예시 3: 복합 조건 (OR)
"device.battery < 10 OR device.signal_strength < 20"

# 예시 4: NOT
"NOT (device.status = 'OFFLINE')"

# 예시 5: IN 연산자
"device.type IN ('AUV', 'ROV')"

# 예시 6: BETWEEN
"device.depth BETWEEN 100 AND 500"

# 예시 7: LIKE (문자열 패턴)
"device.device_id LIKE 'aauv*'"

# 예시 8: 조합
"(device.battery < 20 AND device.type = 'AUV') OR (device.signal_strength < 10)"
```

---

## 3. Rule 액션 정의

### 3.1 액션 타입

#### 1) ALERT - 경고 발행

```python
{
    "type": "ALERT",
    "severity": "INFO|WARNING|CRITICAL",
    "message": "배터리 부족: {{ device.device_id }} ({{ device.battery_percent }}%)",
    "target_agents": ["SystemSentinel", "PolicyManager"]
}
```

**사용 예**:
- 배터리 30% → WARNING 경고
- 신호 손실 → CRITICAL 경고
- Task 완료 → INFO 알림

---

#### 2) AUTO_TASK - 자동 Task 생성

```python
{
    "type": "AUTO_TASK",
    "task_title": "배터리 충전을 위해 기지로 복귀",
    "required_action": "RETURN_TO_BASE",
    "parameters": {
        "target_location": "base_station",
        "priority": "HIGH"
    },
    "timeout_sec": 600,
    "auto_create_mission": True,  # Mission을 자동 생성할 것인가?
    "device_filter": {
        "type": "AUV",
        "status": "ONLINE"
    }  # 여러 Device에 할당 가능한 경우
}
```

**사용 예**:
- 배터리 < 10% → RETURN_TO_BASE Task 자동 생성
- 통신 단절 → HOLD_POSITION Task 자동 생성
- Task 실패 → 대체 Device로 재할당

---

#### 3) DEVICE_STATE_CHANGE - Device 상태 변경

```python
{
    "type": "DEVICE_STATE_CHANGE",
    "target_device_id": "aauv-01",  # 특정 Device 또는 "{{device.device_id}}" 템플릿
    "new_status": "OFFLINE|DEGRADED|REMOVED"
}
```

**사용 예**:
- Heartbeat 타임아웃 → OFFLINE 처리
- 센서 이상 감지 → DEGRADED 처리
- 유지보수 필요 → REMOVED 처리

---

#### 4) POLICY_EXECUTE - 다른 Policy 실행

```python
{
    "type": "POLICY_EXECUTE",
    "target_policy_id": "safe-mode-policy",
    "parameters": {
        "reason": "신호 약화 감지",
        "emergency_level": "HIGH"
    }
}
```

**사용 예**:
- 신호 약화 + 배터리 저하 → "안전 모드" Policy 실행
- 센서 여러 개 오류 → "위기 대응" Policy 실행

---

#### 5) NOTIFY - 사용자 알림 (향후 확장)

```python
{
    "type": "NOTIFY",
    "channels": ["slack", "email", "sms"],
    "recipients": ["operator@example.com"],
    "message": "{{ device.device_id }} 배터리 부족: {{ device.battery_percent }}%",
    "priority": "HIGH"
}
```

---

### 3.2 액션 템플릿 변수

Rule 액션에서 Event 데이터를 참조 가능:

```python
# 예시
{
    "type": "ALERT",
    "message": "Device {{ device.device_id }} 배터리: {{ device.battery_percent }}%"
}

# 결과 (Event 수신 시)
"message": "Device aauv-01 배터리: 25%"
```

---

## 4. Rule 평가 엔진

### 4.1 조건 평가 로직

```python
class RuleConditionEvaluator:
    """Rule 조건 평가"""
    
    def evaluate(self, condition: str, event_data: Dict[str, Any]) -> bool:
        """
        조건 문자열을 평가
        
        Args:
            condition: "device.battery < 30 AND device.status = 'ONLINE'"
            event_data: Event에서 추출한 데이터
        
        Returns:
            조건 일치 여부 (True/False)
        """
        
        # 1. 조건 파싱
        parsed = self._parse_condition(condition)
        
        # 2. 각 operand 평가
        result = self._evaluate_expr(parsed, event_data)
        
        return result
    
    def _parse_condition(self, condition: str):
        """조건 문자열을 파싱"""
        
        # "device.battery < 30 AND device.status = 'ONLINE'"
        # →
        # {
        #     "operator": "AND",
        #     "left": {"operand": "device.battery", "op": "<", "value": 30},
        #     "right": {"operand": "device.status", "op": "==", "value": "ONLINE"}
        # }
        
        # 간단한 파서 구현 (실제로는 더 복잡할 수 있음)
        # pyparsing 또는 lark 같은 파서 라이브러리 사용 권장
        
        pass
    
    def _evaluate_expr(self, expr, event_data: Dict[str, Any]) -> bool:
        """파싱된 표현식 평가"""
        
        if isinstance(expr, dict):
            if expr.get("type") == "AND":
                return (self._evaluate_expr(expr["left"], event_data) and 
                        self._evaluate_expr(expr["right"], event_data))
            
            elif expr.get("type") == "OR":
                return (self._evaluate_expr(expr["left"], event_data) or 
                        self._evaluate_expr(expr["right"], event_data))
            
            elif expr.get("type") == "NOT":
                return not self._evaluate_expr(expr["operand"], event_data)
            
            elif expr.get("type") == "COMPARISON":
                return self._evaluate_comparison(expr, event_data)
        
        return False
    
    def _evaluate_comparison(self, comparison: Dict, event_data: Dict[str, Any]) -> bool:
        """비교 연산 평가"""
        
        operand_path = comparison["operand"]  # "device.battery"
        operator = comparison["operator"]      # "<"
        expected_value = comparison["value"]   # 30
        
        # Event 데이터에서 값 추출
        actual_value = self._get_value_from_event(operand_path, event_data)
        
        if actual_value is None:
            return False
        
        # 연산자별 평가
        if operator == "==":
            return actual_value == expected_value
        elif operator == "!=":
            return actual_value != expected_value
        elif operator == "<":
            return actual_value < expected_value
        elif operator == ">":
            return actual_value > expected_value
        elif operator == "<=":
            return actual_value <= expected_value
        elif operator == ">=":
            return actual_value >= expected_value
        elif operator == "IN":
            return actual_value in expected_value
        elif operator == "BETWEEN":
            return expected_value[0] <= actual_value <= expected_value[1]
        elif operator == "LIKE":
            # 간단한 와일드카드 매칭
            import fnmatch
            return fnmatch.fnmatch(str(actual_value), str(expected_value))
        
        return False
    
    def _get_value_from_event(self, operand_path: str, event_data: Dict[str, Any]):
        """Event 데이터에서 값 추출"""
        
        # "device.battery" → event_data["device"]["battery"]
        parts = operand_path.split(".")
        value = event_data
        
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return None
        
        return value
```

### 4.2 Rule 매칭 및 실행

```python
class RuleEngine:
    """Rule Engine - Event 처리 및 자동화"""
    
    def __init__(self):
        self.rules = []  # 등록된 Rule 목록
        self.evaluator = RuleConditionEvaluator()
    
    async def process_event(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Event 수신 → Rule 평가 → 자동 실행
        """
        
        matched_rules = []
        event_type = event["event_type"]
        
        # 1. Event 타입과 일치하는 Rule 찾기
        for rule in self.rules:
            if not rule.get("enabled", True):
                continue
            
            trigger = rule.get("trigger", {})
            if trigger.get("event_type") != event_type:
                continue
            
            # 2. 조건 평가
            condition = rule.get("condition")
            if condition and not self.evaluator.evaluate(condition, event):
                continue
            
            matched_rules.append(rule)
        
        # 3. Priority 순서로 정렬 (낮은 번호 = 높은 우선순위)
        matched_rules.sort(key=lambda r: r.get("priority", 100))
        
        # 4. Rule 실행
        results = []
        for rule in matched_rules:
            result = await self._execute_rule(rule, event)
            results.append(result)
        
        return results
    
    async def _execute_rule(self, rule: Dict[str, Any], event: Dict[str, Any]) -> Dict[str, Any]:
        """Rule 실행"""
        
        rule_id = rule["rule_id"]
        action = rule.get("action", {})
        
        try:
            action_type = action.get("type")
            
            if action_type == "ALERT":
                return await self._execute_alert(rule, action, event)
            elif action_type == "AUTO_TASK":
                return await self._execute_auto_task(rule, action, event)
            elif action_type == "DEVICE_STATE_CHANGE":
                return await self._execute_device_state_change(rule, action, event)
            elif action_type == "POLICY_EXECUTE":
                return await self._execute_policy(rule, action, event)
            
            return {"rule_id": rule_id, "status": "unknown_action"}
        
        except Exception as e:
            logger.error(f"Error executing rule {rule_id}: {e}")
            return {"rule_id": rule_id, "status": "failed", "error": str(e)}
    
    async def _execute_alert(self, rule, action, event) -> Dict[str, Any]:
        """ALERT 액션 실행"""
        
        message = action.get("message", "")
        
        # 템플릿 변수 치환
        message = self._substitute_variables(message, event)
        
        # SystemSentinel/PolicyManager에 Alert 발행
        # (실제 구현은 PolicyManager 참고)
        
        return {
            "rule_id": rule["rule_id"],
            "status": "executed",
            "action": "ALERT",
            "message": message
        }
    
    async def _execute_auto_task(self, rule, action, event) -> Dict[str, Any]:
        """AUTO_TASK 액션 실행"""
        
        # Task 생성 후 Mission 할당
        task = {
            "task_id": str(uuid.uuid4()),
            "title": action.get("task_title"),
            "required_action": action.get("required_action"),
            "parameters": action.get("parameters", {}),
            "timeout_sec": action.get("timeout_sec", 300)
        }
        
        # (실제 구현은 MissionPlanner/DeviceBridge 참고)
        
        return {
            "rule_id": rule["rule_id"],
            "status": "executed",
            "action": "AUTO_TASK",
            "task_id": task["task_id"]
        }
    
    def _substitute_variables(self, template: str, event: Dict[str, Any]) -> str:
        """템플릿 변수 치환"""
        
        import re
        
        # "{{ device.battery }}" 패턴 찾기
        pattern = r"\{\{\s*([\w\.]+)\s*\}\}"
        
        def replace_var(match):
            var_path = match.group(1)
            value = self._get_value_from_event(var_path, event)
            return str(value) if value is not None else "N/A"
        
        return re.sub(pattern, replace_var, template)
    
    def _get_value_from_event(self, operand_path: str, event_data: Dict[str, Any]):
        """(evaluator와 동일)"""
        parts = operand_path.split(".")
        value = event_data
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return None
        return value
```

---

## 5. Rule 우선순위 & 충돌 해결

### 5.1 우선순위 결정

```python
# Rule 예시
{
    "rule_id": "rule-battery-critical",
    "priority": 1,  # 가장 높은 우선순위
    "enabled": True,
    "trigger": {"event_type": "DEVICE_HEALTHCHECK"},
    "condition": "device.battery < 10",
    "action": {
        "type": "AUTO_TASK",
        "required_action": "RETURN_TO_BASE",
        "task_title": "긴급: 배터리 충전"
    }
}

# Priority 값이 낮을수록 먼저 실행
# 1 (높음) → 50 (중간) → 100 (낮음)
```

### 5.2 여러 Rule이 매칭될 때

```
Event: Device 배터리 25% + 신호 약화

매칭되는 Rule:
1. rule-battery-warning (priority=10)
   - condition: device.battery < 30
   - action: ALERT(WARNING)

2. rule-signal-warning (priority=20)
   - condition: device.signal_strength < 30
   - action: ALERT(WARNING)

3. rule-safe-mode (priority=5)
   - condition: device.battery < 50 AND device.signal_strength < 50
   - action: POLICY_EXECUTE(safe-mode-policy)

실행 순서: rule-safe-mode(5) → rule-battery-warning(10) → rule-signal-warning(20)
```

---

## 6. Rule 상태 관리

### 6.1 Rule 활성/비활성 토글

```python
# Rule 관리 엔드포인트 (PolicyManager)
@app.put("/rules/{rule_id}/status")
async def toggle_rule_status(rule_id: str, enabled: bool):
    """Rule 활성/비활성 토글"""
    
    rule = await registry.get_rule(rule_id)
    rule["enabled"] = enabled
    rule["updated_at"] = datetime.utcnow().isoformat() + "Z"
    
    await registry.update_rule(rule)
    
    return {"rule_id": rule_id, "enabled": enabled}
```

---

## 7. Rule 저장 구조

### 7.1 Rule 데이터 모델

```python
{
    "rule_id": "rule-battery-critical",
    "name": "배터리 부족 - 긴급",
    "description": "배터리가 10% 이하면 즉시 기지로 복귀",
    "enabled": True,
    "priority": 1,
    
    "trigger": {
        "event_type": "DEVICE_HEALTHCHECK"
    },
    
    "condition": "device.battery <= 10 AND device.status = 'ONLINE'",
    
    "action": {
        "type": "AUTO_TASK",
        "task_title": "긴급 충전",
        "required_action": "RETURN_TO_BASE",
        "parameters": {
            "target_location": "base_station",
            "speed": "HIGH"
        },
        "timeout_sec": 600
    },
    
    "created_by": {"user_id": "admin", "name": "관리자"},
    "created_at": "2026-05-13T10:00:00Z",
    "updated_at": "2026-05-13T10:00:00Z"
}
```

---

## 8. Rule 테스트

### 8.1 단위 테스트

```python
import pytest

class TestRuleConditionEvaluator:
    
    def test_simple_condition(self):
        evaluator = RuleConditionEvaluator()
        
        event = {
            "device": {"battery": 25}
        }
        
        result = evaluator.evaluate("device.battery < 30", event)
        assert result == True
    
    def test_complex_condition_and(self):
        evaluator = RuleConditionEvaluator()
        
        event = {
            "device": {"battery": 25, "status": "ONLINE"}
        }
        
        result = evaluator.evaluate(
            "device.battery < 30 AND device.status = 'ONLINE'",
            event
        )
        assert result == True
    
    def test_complex_condition_or(self):
        evaluator = RuleConditionEvaluator()
        
        event = {
            "device": {"battery": 25, "signal_strength": 50}
        }
        
        result = evaluator.evaluate(
            "device.battery < 20 OR device.signal_strength < 40",
            event
        )
        assert result == True
```

---

## 9. 참고자료

- [system-agent.md](./system-agent.md) - PolicyManager 구현
- [event-types.md](../core/event-types.md) - Event 정의
- [principles.md](../core/principles.md) - 설계 원칙
