# Universal Visualization Agent (UVA) — 프론트엔드 기반 구조

## Context

**Agent가 데이터를 받으면, 그것을 시각화할 최적 방법을 JSON 레이아웃으로 결정하여 프론트에 전달한다.**
프론트는 그 JSON을 읽고 기존 위젯들을 조합하여 UI를 렌더링한다.

**흐름**:
```
Server / External System
    ↓ (데이터 JSON)
Agent (Visualization Decision Logic)
    ↓ (레이아웃 JSON)
Frontend (Widget Renderer)
    ↓
UI 렌더링
```

**백엔드 불필요**: Agent가 직접 레이아웃 JSON을 생성해서 프론트로 전달

---

## 아키텍처

### 1단계: 서버 데이터 스키마 정의

서버(CoWater, Prometheus, MQTT 등)가 보낼 수 있는 데이터 형식 표준화.

```json
{
  "timestamp": "2026-04-20T11:30:00Z",
  "entities": [
    {
      "id": "ship-001",
      "name": "테스트선박",
      "type": "ship",
      "position": {
        "lat": 35.15,
        "lon": 129.15,
        "depth": null
      },
      "status": "normal",
      "metadata": {
        "sog": 12.5,
        "heading": 90,
        "battery": 85,
        "cpa": 2.1
      }
    }
  ],
  "events": [
    {
      "id": "alert-001",
      "entity_id": "ship-001",
      "type": "collision_risk",
      "severity": "critical",
      "message": "충돌 위험 감지",
      "timestamp": "2026-04-20T11:30:00Z",
      "details": {
        "cpa": 2.1,
        "tcpa": 8,
        "target_id": "ship-002"
      }
    }
  ],
  "links": [
    {
      "id": "link-001",
      "source_id": "ship-001",
      "target_id": "ship-002",
      "type": "communication",
      "status": "active",
      "metadata": {}
    }
  ],
  "metrics": [
    {
      "id": "metric-001",
      "entity_id": "ship-001",
      "name": "battery",
      "value": 85,
      "unit": "%",
      "timestamp": "2026-04-20T11:30:00Z",
      "threshold": 20
    }
  ]
}
```

**요점**: 서버는 항상 이 형식으로 데이터를 전달. 종류/필드는 자유롭게 확장 가능 (metadata).

---

### 2단계: Agent의 레이아웃 JSON 결정

Agent는 받은 데이터를 분석하고, "어떤 위젯을 어디에 배치할지" 정하는 **레이아웃 JSON**을 생성한다.

```json
{
  "situation": "emergency",
  "focus_entity_id": "ship-001",
  "panels": [
    {
      "id": "panel-alert-list",
      "type": "alert_list",
      "position": {
        "x": 0,
        "y": 0,
        "width": 30,
        "height": 100
      },
      "config": {
        "severity_filter": ["critical", "warning"],
        "sort_by": "timestamp",
        "max_items": 10
      }
    },
    {
      "id": "panel-map",
      "type": "map_2d",
      "position": {
        "x": 30,
        "y": 0,
        "width": 70,
        "height": 70
      },
      "config": {
        "center": [35.15, 129.15],
        "zoom": 12,
        "focus_entity": "ship-001",
        "show_entity_types": ["ship", "usv", "drone"],
        "show_links": true,
        "show_trails": true
      }
    },
    {
      "id": "panel-entity-detail",
      "type": "entity_detail",
      "position": {
        "x": 30,
        "y": 70,
        "width": 70,
        "height": 30
      },
      "config": {
        "entity_id": "ship-001",
        "show_fields": ["name", "position", "status", "sog", "heading", "battery", "cpa"]
      }
    }
  ],
  "recommendations": [
    {
      "type": "action",
      "priority": "high",
      "message": "충돌 위험: ship-001 vs ship-002, CPA 2.1nm, TCPA 8분",
      "suggested_action": "focus_entity",
      "target": "ship-001"
    }
  ]
}
```

**핵심**:
- `panels`: 사용 가능한 위젯들을 어디에 배치할지
- `config`: 각 위젯이 받을 데이터 필터링/포맷팅 옵션
- `recommendations`: 사용자에게 할 제안

---

### 3단계: 프론트엔드 위젯 라이브러리

기존 위젯들을 catalog로 관리. Agent는 이 catalog의 위젯들을 조합.

```typescript
// frontend/src/core/widget_catalog.ts

export type WidgetType = 
  | "map_2d"
  | "scene_3d"
  | "alert_list"
  | "entity_list"
  | "entity_detail"
  | "kpi_dashboard"
  | "timeline"
  | "entity_trajectory"
  | "communication_links"
  | "event_log"
  | "system_status"
  | "recommendation_card"
  | "metrics_chart"

export interface WidgetDefinition {
  id: string
  type: WidgetType
  position: {
    x: number    // 0-100 (%)
    y: number    // 0-100 (%)
    width: number  // 0-100 (%)
    height: number // 0-100 (%)
  }
  config: Record<string, any>  // 위젯별 커스텀 설정
}

export interface LayoutJSON {
  situation: string
  focus_entity_id?: string
  panels: WidgetDefinition[]
  recommendations: Array<{
    type: string
    priority: "high" | "medium" | "low"
    message: string
    suggested_action?: string
    target?: string
  }>
}
```

### 위젯 구현 예시

```typescript
// frontend/src/widgets/Map2DWidget.tsx

interface Map2DConfig {
  center: [number, number]
  zoom: number
  focus_entity?: string
  show_entity_types: string[]
  show_links: boolean
  show_trails: boolean
}

export function Map2DWidget(props: {
  data: DataFromServer
  config: Map2DConfig
}) {
  const { data, config } = props
  
  // config에 따라 필터링
  const visibleEntities = data.entities.filter(e =>
    config.show_entity_types.includes(e.type)
  )
  
  // MapLibre 렌더링
  return (
    <MapContainer
      center={config.center}
      zoom={config.zoom}
      entities={visibleEntities}
      focusEntity={config.focus_entity}
      links={config.show_links ? data.links : []}
      // ...
    />
  )
}

// frontend/src/widgets/AlertListWidget.tsx

interface AlertListConfig {
  severity_filter: string[]
  sort_by: string
  max_items: number
}

export function AlertListWidget(props: {
  data: DataFromServer
  config: AlertListConfig
}) {
  const { data, config } = props
  
  let alerts = data.events.filter(e =>
    config.severity_filter.includes(e.severity)
  )
  
  if (config.sort_by === "timestamp") {
    alerts = alerts.sort((a, b) =>
      new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
    )
  }
  
  alerts = alerts.slice(0, config.max_items)
  
  return (
    <div className="alert-list">
      {alerts.map(alert => (
        <AlertItem key={alert.id} alert={alert} />
      ))}
    </div>
  )
}

// frontend/src/widgets/EntityDetailWidget.tsx

interface EntityDetailConfig {
  entity_id: string
  show_fields: string[]
}

export function EntityDetailWidget(props: {
  data: DataFromServer
  config: EntityDetailConfig
}) {
  const { data, config } = props
  
  const entity = data.entities.find(e => e.id === config.entity_id)
  if (!entity) return <div>Entity not found</div>
  
  return (
    <div className="entity-detail">
      <h3>{entity.name}</h3>
      <dl>
        {config.show_fields.map(field => (
          <React.Fragment key={field}>
            <dt>{field}</dt>
            <dd>{entity[field] ?? entity.metadata[field]}</dd>
          </React.Fragment>
        ))}
      </dl>
    </div>
  )
}
```

---

### 4단계: 프론트엔드 레이아웃 엔진

레이아웃 JSON을 받아 실제 UI를 렌더링한다.

```typescript
// frontend/src/core/layout_engine.tsx

import { Map2DWidget } from '@/widgets/Map2DWidget'
import { AlertListWidget } from '@/widgets/AlertListWidget'
import { EntityDetailWidget } from '@/widgets/EntityDetailWidget'
// ... 다른 위젯들

const WIDGET_COMPONENTS = {
  map_2d: Map2DWidget,
  alert_list: AlertListWidget,
  entity_detail: EntityDetailWidget,
  entity_list: EntityListWidget,
  kpi_dashboard: KPIDashboardWidget,
  timeline: TimelineWidget,
  // ...
}

interface LayoutEngineProps {
  layout: LayoutJSON
  data: DataFromServer
}

export function LayoutEngine({ layout, data }: LayoutEngineProps) {
  return (
    <div className="layout-container">
      {/* 상황 표시 */}
      <div className="situation-bar">
        <SituationIndicator situation={layout.situation} />
      </div>

      {/* 추천 카드 */}
      {layout.recommendations.length > 0 && (
        <div className="recommendations">
          {layout.recommendations.map((rec, idx) => (
            <RecommendationCard key={idx} recommendation={rec} />
          ))}
        </div>
      )}

      {/* 패널 렌더링 */}
      <div className="panels-container">
        {layout.panels.map(panel => {
          const WidgetComponent = WIDGET_COMPONENTS[panel.type]
          if (!WidgetComponent) {
            return <div key={panel.id}>Unknown widget: {panel.type}</div>
          }

          return (
            <div
              key={panel.id}
              className="panel"
              style={{
                left: `${panel.position.x}%`,
                top: `${panel.position.y}%`,
                width: `${panel.position.width}%`,
                height: `${panel.position.height}%`,
              }}
            >
              <WidgetComponent data={data} config={panel.config} />
            </div>
          )
        })}
      </div>
    </div>
  )
}
```

---

## 프로젝트 구조

```
universal-viz-agent/          ← 독립 프로젝트 (어디든 배포 가능)
│
├── frontend/                  # Vite + React 프론트엔드
│   ├── src/
│   │   ├── core/
│   │   │   ├── contracts.ts           # ★ 데이터/레이아웃 타입 정의
│   │   │   ├── layout_engine.tsx      # ★ JSON → UI 렌더러
│   │   │   ├── widget_catalog.ts      # ★ 위젯 카탈로그 (type 목록)
│   │   │   └── hooks/
│   │   │       └── useVisualization.ts  # 데이터/레이아웃 수신 훅
│   │   │
│   │   ├── widgets/                   # ★ 위젯 컴포넌트 (JSON으로 조합)
│   │   │   ├── Map2DWidget.tsx        # Phase 1
│   │   │   ├── AlertListWidget.tsx    # Phase 1
│   │   │   ├── EntityDetailWidget.tsx # Phase 1
│   │   │   ├── EntityListWidget.tsx   # Phase 1
│   │   │   ├── KPIDashboardWidget.tsx # Phase 1
│   │   │   ├── Scene3DWidget.tsx      # Phase 2
│   │   │   ├── TimelineWidget.tsx     # Phase 2
│   │   │   ├── EntityTrajectoryWidget.tsx  # Phase 2
│   │   │   ├── CommunicationLinksWidget.tsx # Phase 2
│   │   │   ├── EventLogWidget.tsx     # Phase 2
│   │   │   ├── SystemStatusWidget.tsx # Phase 2
│   │   │   └── MetricsChartWidget.tsx # Phase 2
│   │   │
│   │   ├── components/
│   │   │   ├── SituationIndicator.tsx
│   │   │   ├── RecommendationCard.tsx
│   │   │   ├── Header.tsx
│   │   │   └── TopBar.tsx
│   │   │
│   │   ├── App.tsx                    # 메인 진입점
│   │   ├── App.css
│   │   └── main.tsx
│   │
│   ├── public/
│   │   └── index.html
│   │
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── package.json
│   └── .env.example
│
├── docs/
│   ├── DATA_SCHEMA.md         # 서버 데이터 스키마
│   ├── LAYOUT_JSON.md         # Agent의 레이아웃 JSON 포맷
│   ├── WIDGET_CATALOG.md      # 위젯 카탈로그 + config
│   ├── INTEGRATION_GUIDE.md   # 외부 시스템 연동 가이드
│   └── EXAMPLES.md            # 레이아웃 JSON 예제들
│
├── README.md                  # 프로젝트 소개
├── LICENSE
└── .gitignore
```

**핵심**:
- **frontend/** — 온전한 독립 Vite/React 앱
- **docs/** — 데이터/레이아웃 스키마 문서화
- **위젯은 catalog** — 각 위젯이 JSON config 기반으로 동작
- **도메인 무관** — 모든 데이터 소스와 Agent와 호환

---

## 사용 방식

### 1. Agent가 데이터를 받음

```python
# 어디든 — Agent 로직
def analyze_and_create_layout(server_data: dict) -> dict:
    """
    서버 데이터 받음 → 분석 → 레이아웃 JSON 생성
    """
    
    # 상황 분류
    situation = classify_situation(server_data)
    
    # 데이터 분석에 따라 레이아웃 결정
    if situation == "emergency":
        layout = {
            "situation": "emergency",
            "focus_entity_id": find_critical_entity(server_data),
            "panels": [
                {
                    "id": "alert-list",
                    "type": "alert_list",
                    "position": {"x": 0, "y": 0, "width": 30, "height": 100},
                    "config": {"severity_filter": ["critical", "warning"]}
                },
                {
                    "id": "map",
                    "type": "map_2d",
                    "position": {"x": 30, "y": 0, "width": 70, "height": 70},
                    "config": {"focus_entity": find_critical_entity(server_data)}
                },
                # ...
            ],
            "recommendations": [
                {
                    "type": "action",
                    "priority": "high",
                    "message": "충돌 위험 감지",
                    "suggested_action": "focus_entity"
                }
            ]
        }
    elif situation == "warning":
        layout = {
            # warning 상황별 레이아웃
        }
    else:
        layout = {
            # normal 상황 기본 레이아웃
        }
    
    return layout

# 프론트로 전달
layout_json = analyze_and_create_layout(server_data)
send_to_frontend(layout_json)
```

### 2. 프론트가 레이아웃 JSON을 받아 렌더링

```typescript
// App.tsx
export function App() {
  const [layoutJson, setLayoutJson] = useState<LayoutJSON | null>(null)
  const [serverData, setServerData] = useState<DataFromServer | null>(null)

  // Agent에서 레이아웃 JSON 받음 (IPC, HTTP, WebSocket 등)
  useEffect(() => {
    const listener = (data: { layout: LayoutJSON; data: DataFromServer }) => {
      setLayoutJson(data.layout)
      setServerData(data.data)
    }

    window.addEventListener('visualization-update', listener)
    return () => window.removeEventListener('visualization-update', listener)
  }, [])

  if (!layoutJson || !serverData) {
    return <div>Waiting for layout...</div>
  }

  return <LayoutEngine layout={layoutJson} data={serverData} />
}
```

---

## Phase 1: 기반 구축 (프론트엔드 + 스키마)

**목표**: 레이아웃 JSON을 읽어 위젯을 조합하고 렌더링하는 완전한 프론트엔드 구현

**구현 항목**:

| 항목 | 파일 | 설명 |
|------|------|------|
| **타입 정의** | `src/core/contracts.ts` | DataFromServer, LayoutJSON, WidgetDefinition |
| **레이아웃 엔진** | `src/core/layout_engine.tsx` | JSON → 동적 UI 렌더러 |
| **위젯 카탈로그** | `src/core/widget_catalog.ts` | 5개 위젯 타입 정의 |
| **수신 훅** | `src/core/hooks/useVisualization.ts` | Agent로부터 데이터/레이아웃 수신 |
| **위젯 구현** | `src/widgets/` (5개) | Map2D, AlertList, EntityDetail, EntityList, KPIDashboard |
| **UI 컴포넌트** | `src/components/` | SituationIndicator, RecommendationCard |
| **데이터 스키마** | `docs/DATA_SCHEMA.md` | 서버가 보낼 데이터 형식 |
| **레이아웃 스키마** | `docs/LAYOUT_JSON.md` | Agent가 생성할 레이아웃 형식 |
| **위젯 문서** | `docs/WIDGET_CATALOG.md` | 각 위젯의 type, config 명세 |
| **예제** | `docs/EXAMPLES.md` | mock layout + mock data |
| **프로젝트 설정** | `vite.config.ts`, `package.json` | Vite + TypeScript + React |

**구현 순서**:
1. 타입 정의 (contracts.ts)
2. 스키마 문서 작성 (DATA_SCHEMA.md, LAYOUT_JSON.md)
3. 위젯 카탈로그 정의 (widget_catalog.ts)
4. 레이아웃 엔진 구현 (layout_engine.tsx)
5. 5개 위젯 구현
6. 수신 훅 구현 (useVisualization.ts)
7. App 메인 로직
8. Mock 예제 작성 (EXAMPLES.md)

**완성 기준**:
- ✅ Agent가 생성한 JSON을 정확히 읽어 렌더링
- ✅ 위젯 위치, 크기, config가 JSON에 정확히 반영
- ✅ situation 변경 → 자동 레이아웃 전환
- ✅ 각 위젯이 독립적으로 데이터 필터링 (config 기반)
- ✅ Mock 데이터/레이아웃으로 동작 검증
- ✅ 도메인 특화 코드 없음 (모두 JSON-driven)

---

## Phase 2: 위젯 확장 (선택사항)

추가 위젯 구현 (Phase 1 완료 후):
- **scene_3d** — Three.js 기반 3D 장면
- **timeline** — 시간축 시각화 (과거/현재/예측)
- **communication_links** — 통신 연결선 표시
- **event_log** — 이벤트 로그 테이블
- **system_status** — 시스템 상태 모니터링
- **metrics_chart** — 시계열 데이터 차트

각 위젯도 동일한 패턴: `config` 기반 필터링/포맷팅

---

## Phase 3: Agent 로직 구현 (별도 프로젝트)

어디서든 Agent 구현 가능 (Python, Node.js, Rust, etc):

```python
# viz_agent.py (Python 예제)
def create_layout(server_data: dict) -> dict:
    """서버 데이터 → 레이아웃 JSON"""
    
    # 1. 상황 분류
    situation = analyze_situation(server_data)
    
    # 2. 레이아웃 결정
    layout = {
        "situation": situation,
        "focus_entity_id": find_focus(server_data, situation),
        "panels": select_panels(situation),  # 우선순위 기반
        "recommendations": generate_recommendations(server_data)
    }
    
    return layout

# 사용
server_data = receive_from_source()  # 어디서든 가능
layout_json = create_layout(server_data)
send_to_frontend(layout_json)
```

**핵심**: Agent는 프론트엔드 무관. 레이아웃 JSON만 생성하면 됨.

---

## 사용 패턴

### 어디서든 Agent 로직 구현

Agent는 다음 흐름을 따름:
1. 데이터 소스에서 데이터 수신 (CoWater REST, Prometheus, MQTT, DB 등)
2. 서버 데이터 스키마로 정규화
3. 분석 → 레이아웃 JSON 생성
4. 프론트로 전달 (IPC, HTTP, WebSocket, 파일 등)

### CoWater 예제

```python
# services/core/viz_bridge.py (또는 별도 에이전트)
import asyncio
import json
from typing import Dict

class VisualizationAgent:
    def analyze_and_create_layout(self, server_data: Dict) -> Dict:
        """데이터 → 레이아웃 JSON"""
        
        # 1. 상황 분류
        critical_count = sum(1 for e in server_data["events"] 
                           if e["severity"] == "critical")
        if critical_count > 0:
            situation = "emergency"
        elif len(server_data["events"]) > 3:
            situation = "warning"
        else:
            situation = "normal"
        
        # 2. 포커스 결정
        focus_entity = (
            server_data["events"][0]["entity_id"]
            if server_data["events"] 
            else None
        )
        
        # 3. 레이아웃 결정
        layout = {
            "situation": situation,
            "focus_entity_id": focus_entity,
            "panels": [
                {
                    "id": "map",
                    "type": "map_2d",
                    "position": {"x": 30, "y": 0, "width": 70, "height": 70},
                    "config": {
                        "center": [35.15, 129.15],
                        "zoom": 12,
                        "focus_entity": focus_entity,
                        "show_entity_types": ["ship", "usv", "drone"],
                        "show_links": True,
                    }
                },
                {
                    "id": "alerts",
                    "type": "alert_list",
                    "position": {"x": 0, "y": 0, "width": 30, "height": 100},
                    "config": {
                        "severity_filter": ["critical", "warning"],
                        "sort_by": "timestamp",
                        "max_items": 10
                    }
                } if situation in ["emergency", "warning"] else None,
                {
                    "id": "detail",
                    "type": "entity_detail",
                    "position": {"x": 30, "y": 70, "width": 70, "height": 30},
                    "config": {
                        "entity_id": focus_entity,
                        "show_fields": ["name", "position", "status", "sog", "heading"]
                    }
                } if focus_entity else None
            ],
            "recommendations": [
                {
                    "type": "action",
                    "priority": "high",
                    "message": f"Critical alert detected on {focus_entity}",
                    "suggested_action": "focus_entity",
                    "target": focus_entity
                }
            ] if situation == "emergency" else []
        }
        
        # None 패널 제거
        layout["panels"] = [p for p in layout["panels"] if p is not None]
        
        return layout

# 사용
agent = VisualizationAgent()

def on_platform_update(platforms, alerts):
    server_data = {
        "timestamp": "2026-04-20T11:30:00Z",
        "entities": [
            {
                "id": p.mmsi,
                "name": p.name,
                "type": "ship",
                "position": {"lat": p.lat, "lon": p.lon, "depth": None},
                "status": "normal",
                "metadata": {"sog": p.sog, "heading": p.heading, "battery": 100}
            }
            for p in platforms
        ],
        "events": [
            {
                "id": a.id,
                "entity_id": a.platform_id,
                "type": a.type,
                "severity": a.severity,
                "message": a.message,
                "timestamp": a.timestamp.isoformat(),
                "details": {}
            }
            for a in alerts
        ],
        "links": [],
        "metrics": []
    }
    
    layout = agent.analyze_and_create_layout(server_data)
    
    # 프론트로 전달 (WebSocket, HTTP, IPC 등)
    send_layout_to_frontend(layout, server_data)
```

### Prometheus 예제

```python
# prometheus_agent.py
def on_prometheus_scrape(metrics_dict):
    """Prometheus → Visualization"""
    
    server_data = {
        "timestamp": datetime.now().isoformat(),
        "entities": [
            {
                "id": job,
                "name": job,
                "type": "service",
                "position": None,
                "status": "normal",
                "metadata": {"instances": count}
            }
            for job, count in metrics_dict.items()
        ],
        "events": [
            {
                "id": f"alert-{i}",
                "entity_id": job,
                "type": "threshold_breach",
                "severity": "warning",
                "message": f"{job} CPU > 80%",
                "timestamp": datetime.now().isoformat(),
                "details": {"metric": "cpu", "value": 85}
            }
            for i, (job, value) in enumerate(metrics_dict.items())
            if value > 80
        ],
        "links": [],
        "metrics": [
            {
                "id": f"metric-{job}",
                "entity_id": job,
                "name": "cpu_usage",
                "value": value,
                "unit": "%",
                "timestamp": datetime.now().isoformat(),
                "threshold": 80
            }
            for job, value in metrics_dict.items()
        ]
    }
    
    layout = agent.analyze_and_create_layout(server_data)
    send_layout_to_frontend(layout, server_data)
```

**핵심**: 어디서든 같은 패턴. 서버 데이터 정규화 → 레이아웃 JSON → 프론트 전달.

---

---

## 검증 체크리스트 (Phase 1 완료 기준)

### 구현 완료
- [ ] 타입 정의 완료 (DataFromServer, LayoutJSON, WidgetDefinition)
- [ ] 레이아웃 엔진 구현 (JSON → 동적 UI 패널 배치)
- [ ] 위젯 카탈로그 정의 (5개 타입)
- [ ] 5개 위젯 구현 (map_2d, alert_list, entity_detail, entity_list, kpi_dashboard)
- [ ] 수신 훅 구현 (useVisualization.ts)
- [ ] 상황 표시 & 추천 카드

### 스키마 문서화
- [ ] DATA_SCHEMA.md (서버 데이터 형식)
- [ ] LAYOUT_JSON.md (레이아웃 JSON 형식 + 예제)
- [ ] WIDGET_CATALOG.md (각 위젯의 type, position, config)
- [ ] EXAMPLES.md (mock 레이아웃 + mock 데이터)

### 기능 검증
- [ ] Mock 데이터 + Mock 레이아웃으로 정확히 렌더링됨
- [ ] 위젯 위치, 크기, config가 JSON에 정확히 반영됨
- [ ] situation 변경 → 자동 레이아웃 전환
- [ ] 각 위젯이 독립적으로 데이터 필터링 (config 기반)
- [ ] 도메인 특화 코드 없음 (모두 JSON-driven)
- [ ] TypeScript strict mode 통과

### 배포 준비
- [ ] Vite 빌드 성공
- [ ] README.md 작성 (설치, 사용법)
- [ ] .env.example 작성
- [ ] Git repo 준비 (독립 오픈소스로 배포 가능)
