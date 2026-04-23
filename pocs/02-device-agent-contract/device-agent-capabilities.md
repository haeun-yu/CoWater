# 02 POC 디바이스-에이전트 기능 분리표

이 문서는 02 POC에서 `Agent`를 붙이기 전에, 각 디바이스가 **직접 처리하는 기능**과 `Agent`가 **판단/계획/전달하는 기능**을 나눈 정리표입니다.

02번 Agent는 `static`과 `dynamic` 두 형태를 모두 가질 수 있습니다.
- `static` Agent는 규칙 기반으로만 동작할 수 있습니다.
- `dynamic` Agent는 컨텍스트를 반영해 더 유연하게 판단할 수 있습니다.
- LLM은 선택사항이며, 반드시 사용하지 않아도 됩니다.
- Agent 구현은 `USVAgent`, `AUVAgent`, `ROVAgent`처럼 타입별로 분리합니다.

대상 디바이스는 `usv`, `auv`, `rov`만 포함합니다.

- `control_center`, `control_ship`, `ocean_power_tower`는 이번 Agent 대상에서 제외합니다.
- `device-side`는 디바이스 자체가 실행하거나 센서로 직접 생성할 수 있는 기능입니다.
- `agent-side`는 Agent가 상황을 해석하고, 명령을 조합하고, 디바이스에 전달하는 기능입니다.

## 역할 구분 기준

### Device-side

- 위치, 자세, 깊이, 속도 갱신
- 센서 데이터 생성 및 전송
- 단순 상태 보고
- 받은 명령의 실제 실행

### Agent-side

- 센서/상태 해석
- 경로 계획
- 대상 추적
- 작업 전환 판단
- 충전/복귀 판단
- 조명/카메라/탐사 모드 선택

---

## `usv`

### Device-side 가능

| 기능명 | 설명 |
|---|---|
| `surface_navigation` | 수면 위에서 이동합니다. |
| `position_update` | 현재 위경도와 고도를 갱신합니다. |
| `heading_update` | 방향을 바꾸며 이동합니다. |
| `speed_update` | 속도를 범위 안에서 조정합니다. |
| `gps_report` | GPS 위치 정보를 전송합니다. |
| `imu_report` | 자세, 가속도, 회전 정보를 전송합니다. |
| `sonar_report` | 기본 소나 탐지 정보를 전송합니다. |
| `magnetometer_report` | 자기장/방위 관련 정보를 전송합니다. |

### Agent-side 가능

| 기능명 | 설명 |
|---|---|
| `patrol_route` | 여러 지점을 순서대로 순찰하도록 경로를 만듭니다. |
| `move_to_device` | 특정 디바이스 위치로 이동 명령을 전달합니다. |
| `follow_target` | 특정 대상의 위치를 추적하며 따라가게 합니다. |
| `return_to_base` | 기준 거점이나 출발점으로 복귀시키는 판단을 합니다. |
| `charge_at_tower` | 오션 파워 타워로 가서 충전하도록 지시합니다. |
| `hold_position` | 현재 위치를 유지하거나 저속 대기하게 합니다. |
| `route_move` | 여러 웨이포인트를 연결한 주행 계획을 생성합니다. |

### 추가 필요

| 기능명 | 설명 |
|---|---|
| `dock_control` | 충전 타워에 도킹하는 실제 제어 절차입니다. |
| `collision_avoidance` | 장애물을 피하는 고급 항법입니다. |
| `payload_switch` | 장착 장비 상태를 바꾸는 기능입니다. |
| `mission_abort` | 임무를 중단하고 안전 상태로 전환하는 기능입니다. |

---

## `auv`

### Device-side 가능

| 기능명 | 설명 |
|---|---|
| `subsurface_navigation` | 수중에서 이동합니다. |
| `depth_update` | 깊이 범위 안에서 상하 위치를 갱신합니다. |
| `gps_report` | 수면 근처 또는 위치 참조용 GPS 정보를 전송합니다. |
| `pressure_report` | 압력과 수심 정보를 전송합니다. |
| `side_scan_sonar_report` | 측면 탐색용 소나 데이터를 전송합니다. |
| `temperature_report` | 수온 정보를 전송합니다. |
| `magnetometer_report` | 자기장/방위 정보를 전송합니다. |

### Agent-side 가능

| 기능명 | 설명 |
|---|---|
| `patrol_route` | 수중 탐사 경로를 순서대로 계획합니다. |
| `move_to_device` | 특정 목표 좌표로 이동시키는 명령을 만듭니다. |
| `follow_target` | 대상의 위치를 추적하는 경로를 계산합니다. |
| `return_to_base` | 회수 지점이나 기준점으로 복귀시키는 판단을 합니다. |
| `charge_at_tower` | 수면 복귀 후 충전 위치로 보내는 판단을 합니다. |
| `hold_depth` | 특정 수심을 유지하도록 명령합니다. |
| `surface` | 수면으로 상승시키는 명령을 전달합니다. |

### 추가 필요

| 기능명 | 설명 |
|---|---|
| `terrain_mapping` | 해저 지형을 장기적으로 맵핑하는 기능입니다. |
| `target_classification` | 탐지된 객체를 분류하는 고급 판단입니다. |
| `adaptive_sonar_scan` | 상황에 따라 소나 탐색 범위를 바꾸는 기능입니다. |
| `emergency_buoyancy` | 비상 상승/부상 제어 기능입니다. |

---

## `rov`

### Device-side 가능

| 기능명 | 설명 |
|---|---|
| `deep_navigation` | 깊은 수심 범위에서 이동합니다. |
| `depth_update` | 현재 수심을 갱신합니다. |
| `pressure_report` | 압력/수심 정보를 전송합니다. |
| `hd_camera_stream` | 영상 또는 영상 메타를 전송합니다. |
| `led_light_status` | 조명 밝기와 상태 정보를 전송합니다. |
| `profiling_sonar_report` | 정밀 탐사용 소나 데이터를 전송합니다. |
| `temperature_report` | 온도 정보를 전송합니다. |
| `magnetometer_report` | 자기장/방위 정보를 전송합니다. |

### Agent-side 가능

| 기능명 | 설명 |
|---|---|
| `patrol_route` | 작업 구역을 순회하는 경로를 만듭니다. |
| `move_to_device` | 특정 목표 지점으로 이동시키는 명령을 만듭니다. |
| `follow_target` | 대상 물체를 따라가며 관측하도록 지시합니다. |
| `return_to_base` | 작업 종료 후 회수 위치로 복귀시킵니다. |
| `charge_at_tower` | 충전 거점으로 이동시키는 판단을 합니다. |
| `light_on` | 조명을 켜도록 지시합니다. |
| `light_off` | 조명을 끄도록 지시합니다. |
| `camera_mode_switch` | 카메라 스트림/해상도/촬영 모드를 바꾸는 판단을 합니다. |
| `sonar_scan_plan` | 정밀 탐사용 소나 스캔 계획을 만듭니다. |

### 추가 필요

| 기능명 | 설명 |
|---|---|
| `manipulator_control` | 로봇 팔이나 작업 장비를 직접 제어하는 기능입니다. |
| `object_grab` | 물체를 집거나 옮기는 작업 기능입니다. |
| `tool_switch` | 공구나 장착 장비를 교체하는 기능입니다. |
| `inspection_report` | 검사 결과를 구조화해 요약하는 기능입니다. |

---

## Agent가 공통으로 다룰 수 있는 것

| 기능명 | 설명 |
|---|---|
| `mission_planning` | 임무 전체 흐름을 계획합니다. |
| `task_routing` | 어떤 디바이스에 어떤 작업을 보낼지 결정합니다. |
| `sensor_context_merge` | 여러 센서 값을 합쳐 상황을 해석합니다. |
| `alert_response` | 이상 징후가 있을 때 우선순위를 바꿉니다. |
| `priority_rewrite` | 임무 우선순위를 바꿔 재전달합니다. |
| `stateful_coordination` | 디바이스별 상태를 기억하면서 지시를 조정합니다. |

---

## 정리

- `Device-side`는 **실행**입니다.
- `Agent-side`는 **판단 + 계획 + 전달**입니다.
- `USV`는 수면 이동과 탐색.
- `AUV`는 수중 탐사와 수심 제어.
- `ROV`는 정밀 수중 작업과 영상/조명 제어.

이 구분을 기준으로 02 POC에서는 `Agent -> Device` 명령 구조를 설계하면 됩니다.
