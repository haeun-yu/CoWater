# 프론트엔드 구현 가이드 (Frontend Implementation Guide)

**문서 버전**: v0.1  
**최종 업데이트**: 2026-05-13  
**대상**: 프론트엔드 개발자  
**목적**: CoWater UI 시스템의 기술 스택, 구조, 페이지별 구현 방법

---

## 1. 기술 스택

### 1.1 핵심 프레임워크

| 영역 | 선택 | 이유 |
|------|------|------|
| **Framework** | React 18 + TypeScript | 생태계 가장 풍부, 개발 경험 우수 |
| **상태관리** | Zustand | Redux보다 간단, 보일러플레이트 최소 |
| **UI 컴포넌트** | shadcn/ui | Tailwind 기반, 커스터마이징 용이 |
| **스타일링** | Tailwind CSS | 유틸리티 퍼스트, 일관된 디자인 |
| **3D 시각화** | Three.js + react-three-fiber | WebGL 표준, 성능 우수 |
| **실시간 통신** | WebSocket (native) | Moth MEB pub/sub 연동 |
| **HTTP 클라이언트** | TanStack Query (React Query) | 데이터 페칭 캐싱, 동기화 |
| **라우팅** | React Router v6 | 최신 버전, 좋은 DX |
| **빌드 도구** | Vite | 매우 빠른 빌드, HMR 지원 |

### 1.2 프로젝트 초기화

```bash
# Vite + React + TypeScript 프로젝트 생성
npm create vite@latest cowater-ui -- --template react
cd cowater-ui
npm install

# 필수 라이브러리 설치
npm install zustand @tanstack/react-query axios
npm install three @react-three/fiber @react-three/drei
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p

# shadcn/ui 초기화
npx shadcn-ui@latest init
```

---

## 2. 프로젝트 구조

```
src/
├── pages/                          # 각 페이지 컴포넌트
│   ├── Dashboard.tsx              # 메인 대시보드 (3D 시각화)
│   ├── Proposal.tsx               # Proposal 관리
│   ├── Mission.tsx                # Mission 추적
│   ├── Device.tsx                 # Device 목록 & 상세
│   ├── Policy.tsx                 # Policy/Rule 관리
│   ├── EventLog.tsx               # Event & Alert 로그
│   ├── Analytics.tsx              # 분석 & 보고서
│   ├── Settings.tsx               # 시스템 설정 (ADMIN)
│   ├── Users.tsx                  # 사용자 관리 (ADMIN)
│   └── Chat.tsx                   # Chat Console
│
├── components/                     # 재사용 컴포넌트
│   ├── common/
│   │   ├── Header.tsx
│   │   ├── Sidebar.tsx
│   │   ├── Layout.tsx
│   │   └── ProtectedRoute.tsx
│   │
│   ├── 3d/
│   │   ├── SceneCanvas.tsx        # Three.js 캔버스
│   │   ├── DeviceModel.tsx        # Device 3D 모델
│   │   ├── AgentConnection.tsx    # Agent 연결 시각화
│   │   └── CameraControls.tsx
│   │
│   ├── dashboard/
│   │   ├── DeviceStatus.tsx       # Device 상태 판넬
│   │   ├── DataFlow.tsx           # 실시간 데이터 흐름
│   │   ├── Telemetry.tsx          # 센서 데이터 표시
│   │   └── Stats.tsx              # 통계 위젯
│   │
│   ├── proposal/
│   │   ├── ProposalForm.tsx
│   │   ├── ProposalCard.tsx
│   │   └── TaskPreview.tsx
│   │
│   ├── mission/
│   │   ├── MissionTimeline.tsx
│   │   ├── TaskStatus.tsx
│   │   └── ProgressBar.tsx
│   │
│   └── chat/
│       ├── ChatInput.tsx
│       ├── ChatMessage.tsx
│       └── ChatHistory.tsx
│
├── hooks/                          # 커스텀 Hooks
│   ├── useAuth.ts                 # 인증
│   ├── useDevice.ts               # Device 데이터
│   ├── useMission.ts              # Mission 데이터
│   ├── useWebSocket.ts            # WebSocket 연결
│   ├── useMebSubscribe.ts         # Moth MEB 구독
│   └── usePermission.ts           # 권한 확인
│
├── stores/                         # Zustand 상태 관리
│   ├── authStore.ts               # 인증 상태
│   ├── deviceStore.ts             # Device 상태 (캐시)
│   ├── missionStore.ts            # Mission 상태
│   ├── uiStore.ts                 # UI 상태 (모달, 사이드바 등)
│   └── notificationStore.ts        # 알림 상태
│
├── services/                       # API 통신
│   ├── api.ts                     # Axios 인스턴스
│   ├── authService.ts
│   ├── deviceService.ts
│   ├── missionService.ts
│   ├── policyService.ts
│   ├── reportService.ts
│   └── chatService.ts
│
├── types/                          # TypeScript 타입 정의
│   ├── device.ts
│   ├── mission.ts
│   ├── event.ts
│   ├── policy.ts
│   ├── user.ts
│   └── api.ts
│
├── utils/                          # 유틸리티 함수
│   ├── websocket.ts               # WebSocket 관리
│   ├── meb.ts                     # Moth MEB 구독/발행
│   ├── auth.ts                    # JWT 토큰 관리
│   ├── format.ts                  # 데이터 포매팅
│   └── constants.ts               # 상수
│
├── App.tsx                         # 라우팅 설정
└── main.tsx
```

---

## 3. 핵심 페이지 구현

### 3.1 Dashboard (메인 페이지) - 3D 시각화

```tsx
// src/pages/Dashboard.tsx

import React, { useEffect } from 'react';
import { Suspense } from 'react';
import SceneCanvas from '@/components/3d/SceneCanvas';
import DeviceStatus from '@/components/dashboard/DeviceStatus';
import DataFlow from '@/components/dashboard/DataFlow';
import Telemetry from '@/components/dashboard/Telemetry';
import Stats from '@/components/dashboard/Stats';
import { useDevice } from '@/hooks/useDevice';
import { useMebSubscribe } from '@/hooks/useMebSubscribe';

export default function Dashboard() {
  const { devices, updateDeviceStatus } = useDevice();
  
  // Moth MEB 구독 - 실시간 Device 상태 업데이트
  useMebSubscribe({
    channels: ['agents'],
    eventTypes: ['DEVICE_HEALTHCHECK', 'SYS_TASK_DISPATCHED', 'SYS_ALERT'],
    onMessage: (event) => {
      if (event.event_type === 'DEVICE_HEALTHCHECK') {
        // Device 상태 업데이트
        updateDeviceStatus(event.actor_id, event.data);
      }
    }
  });
  
  return (
    <div className="flex h-screen bg-slate-900">
      {/* 왼쪽: 3D 시각화 (60%) */}
      <div className="flex-1 relative">
        <Suspense fallback={<div className="w-full h-full bg-slate-950 flex items-center justify-center">로딩 중...</div>}>
          <SceneCanvas devices={devices} />
        </Suspense>
      </div>
      
      {/* 오른쪽: 상태 판넬 (40%) */}
      <div className="w-2/5 bg-slate-800 border-l border-slate-700 flex flex-col overflow-hidden">
        {/* 상단: Device 목록 */}
        <div className="flex-1 overflow-y-auto p-4 border-b border-slate-700">
          <h2 className="text-lg font-bold text-white mb-4">Device 상태</h2>
          <DeviceStatus devices={devices} />
        </div>
        
        {/* 중단: 실시간 데이터 흐름 */}
        <div className="flex-1 overflow-y-auto p-4 border-b border-slate-700">
          <h2 className="text-lg font-bold text-white mb-4">데이터 흐름</h2>
          <DataFlow />
        </div>
        
        {/* 하단: 통계 */}
        <div className="flex-1 overflow-y-auto p-4">
          <Stats devices={devices} />
        </div>
      </div>
    </div>
  );
}
```

### 3.2 Chat Console - 자연어 명령

```tsx
// src/pages/Chat.tsx

import React, { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import ChatMessage from '@/components/chat/ChatMessage';
import ChatInput from '@/components/chat/ChatInput';
import { chatService } from '@/services/chatService';

export default function Chat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  
  const requestMutation = useMutation({
    mutationFn: (userInput: string) => chatService.sendMessage(userInput),
    onSuccess: (response) => {
      // 응답 메시지 추가
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: response.message, type: response.type }
      ]);
      setIsLoading(false);
    },
    onError: (error) => {
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: '오류가 발생했습니다.', type: 'error' }
      ]);
      setIsLoading(false);
    }
  });
  
  const handleSendMessage = (input: string) => {
    // 사용자 메시지 추가
    setMessages(prev => [
      ...prev,
      { role: 'user', content: input }
    ]);
    
    setIsLoading(true);
    requestMutation.mutate(input);
  };
  
  return (
    <div className="flex flex-col h-full bg-slate-900">
      {/* 채팅 이력 */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-slate-400 mt-10">
            <p className="text-lg">자연어로 명령을 입력하세요</p>
            <p className="text-sm mt-2">예: "기뢰탐지 해줄래?", "배터리 상태 알려줘"</p>
          </div>
        )}
        
        {messages.map((msg, idx) => (
          <ChatMessage key={idx} message={msg} />
        ))}
        
        {isLoading && (
          <div className="text-slate-400 text-sm">입력 중...</div>
        )}
      </div>
      
      {/* 입력 창 */}
      <div className="border-t border-slate-700 p-4">
        <ChatInput onSend={handleSendMessage} disabled={isLoading} />
      </div>
    </div>
  );
}
```

### 3.3 Proposal 관리 페이지

```tsx
// src/pages/Proposal.tsx

import React, { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import ProposalForm from '@/components/proposal/ProposalForm';
import ProposalCard from '@/components/proposal/ProposalCard';
import { proposalService } from '@/services/proposalService';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';

export default function Proposal() {
  const [isFormOpen, setIsFormOpen] = useState(false);
  
  // Proposal 목록 조회
  const { data: proposals, refetch } = useQuery({
    queryKey: ['proposals'],
    queryFn: proposalService.getProposals
  });
```

### 3.4 Policy & Rule 관리 페이지

```tsx
// src/pages/Policy.tsx

import React, { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import RuleForm from '@/components/policy/RuleForm';
import RuleCard from '@/components/policy/RuleCard';
import RuleTestPanel from '@/components/policy/RuleTestPanel';
import { policyService } from '@/services/policyService';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';

export default function Policy() {
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [selectedRule, setSelectedRule] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  
  // Rule 목록 조회 (검색 필터링)
  const { data: rules, refetch } = useQuery({
    queryKey: ['rules', searchTerm],
    queryFn: () => policyService.getRules({ search: searchTerm })
  });
  
  // Rule 토글 (활성/비활성)
  const toggleRuleMutation = useMutation({
    mutationFn: (ruleId: string) => policyService.toggleRule(ruleId),
    onSuccess: () => refetch()
  });
  
  // Rule 삭제
  const deleteRuleMutation = useMutation({
    mutationFn: (ruleId: string) => policyService.deleteRule(ruleId),
    onSuccess: () => refetch()
  });
  
  return (
    <div className="p-6 bg-slate-900 min-h-screen">
      {/* 상단: 제목 + 생성 버튼 */}
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold text-white">Policy & Rule 관리</h1>
        <button
          onClick={() => setIsFormOpen(true)}
          className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded"
        >
          새 Rule 생성
        </button>
      </div>
      
      {/* 검색 */}
      <div className="mb-6">
        <input
          type="text"
          placeholder="Rule 검색..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="w-full px-4 py-2 rounded bg-slate-800 text-white"
        />
      </div>
      
      {/* 탭: 모든 Rule / 활성 Rule / 비활성 Rule */}
      <div className="mb-6 flex gap-4 border-b border-slate-700">
        <button className="text-blue-400 border-b-2 border-blue-400 pb-2">
          전체 ({rules?.length || 0})
        </button>
        <button className="text-slate-400 pb-2">
          활성 ({rules?.filter(r => r.enabled).length || 0})
        </button>
        <button className="text-slate-400 pb-2">
          비활성 ({rules?.filter(r => !r.enabled).length || 0})
        </button>
      </div>
      
      {/* Rule 목록 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        {rules?.map(rule => (
          <div key={rule.rule_id} className="bg-slate-800 rounded p-4 border border-slate-700">
            <div className="flex justify-between items-start mb-3">
              <div>
                <h3 className="text-lg font-bold text-white">{rule.name}</h3>
                <p className="text-sm text-slate-400">{rule.description}</p>
              </div>
              <div className="flex gap-2">
                {/* 토글 */}
                <button
                  onClick={() => toggleRuleMutation.mutate(rule.rule_id)}
                  className={`px-3 py-1 rounded text-sm ${
                    rule.enabled
                      ? 'bg-green-600 hover:bg-green-700 text-white'
                      : 'bg-slate-700 hover:bg-slate-600 text-slate-300'
                  }`}
                >
                  {rule.enabled ? '활성' : '비활성'}
                </button>
                
                {/* 삭제 */}
                <button
                  onClick={() => deleteRuleMutation.mutate(rule.rule_id)}
                  className="px-3 py-1 rounded text-sm bg-red-600 hover:bg-red-700 text-white"
                >
                  삭제
                </button>
              </div>
            </div>
            
            {/* Rule 세부정보 */}
            <div className="space-y-2 text-sm text-slate-300 mb-3">
              <div>
                <span className="font-semibold">Trigger:</span> {rule.trigger.event_type}
              </div>
              <div>
                <span className="font-semibold">Condition:</span>
                <code className="block bg-slate-900 p-2 rounded mt-1 text-xs text-slate-400">
                  {rule.condition}
                </code>
              </div>
              <div>
                <span className="font-semibold">Action:</span> {rule.action.type}
              </div>
              <div>
                <span className="font-semibold">Priority:</span> {rule.priority}
              </div>
            </div>
            
            {/* 테스트 버튼 */}
            <button
              onClick={() => setSelectedRule(rule.rule_id)}
              className="w-full bg-slate-700 hover:bg-slate-600 text-white px-3 py-2 rounded text-sm"
            >
              이 Rule 테스트
            </button>
          </div>
        ))}
      </div>
      
      {/* Rule 생성 다이얼로그 */}
      <Dialog open={isFormOpen} onOpenChange={setIsFormOpen}>
        <DialogContent className="bg-slate-800 border-slate-700">
          <DialogHeader>
            <DialogTitle className="text-white">새 Rule 생성</DialogTitle>
          </DialogHeader>
          <RuleForm onSuccess={() => {
            setIsFormOpen(false);
            refetch();
          }} />
        </DialogContent>
      </Dialog>
      
      {/* Rule 테스트 패널 */}
      {selectedRule && (
        <RuleTestPanel
          ruleId={selectedRule}
          onClose={() => setSelectedRule(null)}
        />
      )}
    </div>
  );
}
```

**Policy 페이지 컴포넌트** (`src/pages/Policy.tsx`의 확장):

```tsx
// Rule 테스트 컴포넌트
// src/components/policy/RuleTestPanel.tsx

export default function RuleTestPanel({ ruleId, onClose }) {
  const [eventData, setEventData] = useState({
    event_type: 'DEVICE_HEALTHCHECK',
    device: {
      device_id: 'aauv-01',
      battery_percent: 25,
      status: 'ONLINE'
    }
  });
  
  const testMutation = useMutation({
    mutationFn: () => policyService.testRule(ruleId, eventData),
    onSuccess: (result) => {
      // 테스트 결과 표시
      setTestResult(result);
    }
  });
  
  return (
    <div className="fixed bottom-0 right-0 bg-slate-800 border border-slate-700 rounded-t p-4 w-96 max-h-96 overflow-y-auto">
      <div className="flex justify-between mb-4">
        <h3 className="text-white font-bold">Rule 테스트</h3>
        <button onClick={onClose} className="text-slate-400">✕</button>
      </div>
      
      {/* Event 데이터 입력 */}
      <textarea
        value={JSON.stringify(eventData, null, 2)}
        onChange={(e) => setEventData(JSON.parse(e.target.value))}
        className="w-full h-32 p-2 bg-slate-900 text-slate-300 rounded mb-4 text-sm"
      />
      
      {/* 테스트 실행 */}
      <button
        onClick={() => testMutation.mutate()}
        className="w-full bg-blue-600 hover:bg-blue-700 text-white py-2 rounded"
      >
        테스트 실행
      </button>
      
      {/* 결과 */}
      {testResult && (
        <div className="mt-4 p-3 bg-slate-900 rounded text-sm">
          <div className="text-green-400">
            조건 일치: {testResult.condition_matched ? '✓' : '✗'}
          </div>
          <div className="text-yellow-400">
            Action: {testResult.action.type}
          </div>
        </div>
      )}
    </div>
  );
}
```

**Policy Service API**:

```ts
// src/services/policyService.ts

export const policyService = {
  // Rule 목록 조회
  getRules: async (filters?: { search?: string }) => {
    const response = await api.get('/rules', { params: filters });
    return response.data;
  },
  
  // Rule 상세 조회
  getRule: async (ruleId: string) => {
    const response = await api.get(`/rules/${ruleId}`);
    return response.data;
  },
  
  // Rule 생성
  createRule: async (rule: Rule) => {
    const response = await api.post('/rules', rule);
    return response.data;
  },
  
  // Rule 수정
  updateRule: async (ruleId: string, updates: Partial<Rule>) => {
    const response = await api.put(`/rules/${ruleId}`, updates);
    return response.data;
  },
  
  // Rule 삭제
  deleteRule: async (ruleId: string) => {
    const response = await api.delete(`/rules/${ruleId}`);
    return response.data;
  },
  
  // Rule 활성/비활성 토글
  toggleRule: async (ruleId: string) => {
    const response = await api.patch(`/rules/${ruleId}/status`);
    return response.data;
  },
  
  // Rule 테스트 (조건 평가 시뮬레이션)
  testRule: async (ruleId: string, eventData: any) => {
    const response = await api.post(`/rules/${ruleId}/test`, {
      event_data: eventData
    });
    return response.data;
  }
};
  
  // Proposal 승인 Mutation
  const approveMutation = useMutation({
    mutationFn: (proposalId: string) => proposalService.approveProposal(proposalId),
    onSuccess: () => refetch()
  });
  
  // Proposal 거부 Mutation
  const rejectMutation = useMutation({
    mutationFn: (proposalId: string) => proposalService.rejectProposal(proposalId),
    onSuccess: () => refetch()
  });
  
  return (
    <div className="p-6 bg-slate-900 min-h-screen">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold text-white">Proposal 관리</h1>
        <button
          onClick={() => setIsFormOpen(true)}
          className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded"
        >
          새 Proposal 생성
        </button>
      </div>
      
      {/* Proposal 목록 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {proposals?.map(proposal => (
          <ProposalCard
            key={proposal.proposal_id}
            proposal={proposal}
            onApprove={() => approveMutation.mutate(proposal.proposal_id)}
            onReject={() => rejectMutation.mutate(proposal.proposal_id)}
          />
        ))}
      </div>
      
      {/* Proposal 생성 다이얼로그 */}
      <Dialog open={isFormOpen} onOpenChange={setIsFormOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>새 Proposal 생성</DialogTitle>
          </DialogHeader>
          <ProposalForm onSuccess={() => {
            setIsFormOpen(false);
            refetch();
          }} />
        </DialogContent>
      </Dialog>
    </div>
  );
}
```

---

## 4. 실시간 데이터 업데이트 (WebSocket + Moth MEB)

### 4.1 WebSocket 관리

```ts
// src/utils/websocket.ts

class WebSocketManager {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 3000;
  
  constructor(private url: string) {}
  
  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      try {
        this.ws = new WebSocket(this.url);
        
        this.ws.onopen = () => {
          console.log('WebSocket connected');
          this.reconnectAttempts = 0;
          resolve();
        };
        
        this.ws.onerror = (error) => {
          console.error('WebSocket error:', error);
          reject(error);
        };
        
        this.ws.onclose = () => {
          console.log('WebSocket disconnected');
          this.attemptReconnect();
        };
      } catch (error) {
        reject(error);
      }
    });
  }
  
  subscribe(channel: string, callback: (message: any) => void) {
    if (!this.ws) return;
    
    this.ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      if (message.channel === channel) {
        callback(message);
      }
    };
  }
  
  publish(channel: string, message: any) {
    if (!this.ws) {
      console.warn('WebSocket not connected');
      return;
    }
    
    this.ws.send(JSON.stringify({
      channel,
      message
    }));
  }
  
  private attemptReconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
      
      console.log(`Reconnecting in ${delay}ms...`);
      setTimeout(() => this.connect(), delay);
    }
  }
  
  disconnect() {
    if (this.ws) {
      this.ws.close();
    }
  }
}

export const wsManager = new WebSocketManager(
  `ws://${process.env.REACT_APP_SERVER_HOST}:${process.env.REACT_APP_WS_PORT}`
);
```

### 4.2 Moth MEB 구독 Hook

```ts
// src/hooks/useMebSubscribe.ts

import { useEffect } from 'react';
import { wsManager } from '@/utils/websocket';

interface SubscribeOptions {
  channels: string[];
  eventTypes?: string[];
  onMessage: (event: any) => void;
}

export function useMebSubscribe({
  channels,
  eventTypes,
  onMessage
}: SubscribeOptions) {
  useEffect(() => {
    // WebSocket 연결
    wsManager.connect().catch(console.error);
    
    // Moth MEB 채널 구독
    channels.forEach(channel => {
      wsManager.subscribe(channel, (message) => {
        // Event type 필터링
        if (eventTypes && !eventTypes.includes(message.event_type)) {
          return;
        }
        
        onMessage(message);
      });
    });
    
    return () => {
      // cleanup은 필요에 따라 (보통 컴포넌트 언마운트 시에만)
    };
  }, [channels, eventTypes, onMessage]);
}
```

---

## 5. 상태 관리 (Zustand)

### 5.1 Device Store

```ts
// src/stores/deviceStore.ts

import create from 'zustand';
import { Device } from '@/types/device';

interface DeviceStore {
  devices: Map<string, Device>;
  addDevice: (device: Device) => void;
  updateDevice: (deviceId: string, updates: Partial<Device>) => void;
  getDevice: (deviceId: string) => Device | undefined;
}

export const useDeviceStore = create<DeviceStore>((set, get) => ({
  devices: new Map(),
  
  addDevice: (device) => {
    set(state => {
      const newDevices = new Map(state.devices);
      newDevices.set(device.device_id, device);
      return { devices: newDevices };
    });
  },
  
  updateDevice: (deviceId, updates) => {
    set(state => {
      const newDevices = new Map(state.devices);
      const device = newDevices.get(deviceId);
      if (device) {
        newDevices.set(deviceId, { ...device, ...updates });
      }
      return { devices: newDevices };
    });
  },
  
  getDevice: (deviceId) => {
    return get().devices.get(deviceId);
  }
}));
```

### 5.2 Auth Store

```ts
// src/stores/authStore.ts

import create from 'zustand';
import { User } from '@/types/user';

interface AuthStore {
  user: User | null;
  token: string | null;
  setAuth: (user: User, token: string) => void;
  logout: () => void;
  hasPermission: (permission: string) => boolean;
}

export const useAuthStore = create<AuthStore>((set, get) => ({
  user: null,
  token: localStorage.getItem('auth_token'),
  
  setAuth: (user, token) => {
    localStorage.setItem('auth_token', token);
    set({ user, token });
  },
  
  logout: () => {
    localStorage.removeItem('auth_token');
    set({ user: null, token: null });
  },
  
  hasPermission: (permission) => {
    const { user } = get();
    if (!user) return false;
    
    // RBAC (Role-Based Access Control)
    const rolePermissions: Record<string, string[]> = {
      'ADMIN': ['*'],  // 모든 권한
      'OPERATOR': ['mission_create', 'mission_view', 'device_control'],
      'VIEWER': ['mission_view', 'device_view']
    };
    
    const permissions = rolePermissions[user.role] || [];
    return permissions.includes('*') || permissions.includes(permission);
  }
}));
```

---

## 6. API 서비스 (TanStack Query)

### 6.1 API 인스턴스

```ts
// src/services/api.ts

import axios from 'axios';
import { useAuthStore } from '@/stores/authStore';

const api = axios.create({
  baseURL: process.env.REACT_APP_API_URL || 'http://localhost:9116',
  timeout: 10000
});

// Request interceptor - 토큰 추가
api.interceptors.request.use(
  config => {
    const { token } = useAuthStore.getState();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  error => Promise.reject(error)
);

// Response interceptor - 401 처리
api.interceptors.response.use(
  response => response,
  error => {
    if (error.response?.status === 401) {
      useAuthStore.getState().logout();
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default api;
```

### 6.2 Mission Service

```ts
// src/services/missionService.ts

import api from './api';
import { Mission, Task } from '@/types/mission';
import { useQuery, useMutation } from '@tanstack/react-query';

export const missionService = {
  // Mission 목록 조회
  getMissions: async () => {
    const response = await api.get('/missions');
    return response.data;
  },
  
  // Mission 상세 조회
  getMission: async (missionId: string) => {
    const response = await api.get(`/missions/${missionId}`);
    return response.data;
  },
  
  // Mission Task 조회
  getMissionTasks: async (missionId: string) => {
    const response = await api.get(`/missions/${missionId}/tasks`);
    return response.data;
  }
};

// React Query Hook
export function useMission(missionId: string) {
  return useQuery({
    queryKey: ['mission', missionId],
    queryFn: () => missionService.getMission(missionId),
    refetchInterval: 2000  // 2초마다 갱신
  });
}
```

---

## 7. TypeScript 타입 정의

### 7.1 Device 타입

```ts
// src/types/device.ts

export interface Device {
  device_id: string;
  type: 'USV' | 'AUV' | 'ROV';
  name: string;
  status: 'ONLINE' | 'OFFLINE' | 'DEGRADED' | 'REMOVED';
  battery_percent: number;
  signal_strength: number;
  position: {
    lat: number;
    lon: number;
  };
  depth?: number;
  environment_state: 'SURFACE' | 'UNDERWATER';
  last_heartbeat_at: string;
  created_at: string;
  updated_at: string;
}
```

### 7.2 Mission 타입

```ts
// src/types/mission.ts

export interface Mission {
  mission_id: string;
  source_proposal_id: string;
  status: 'READY' | 'IN_PROGRESS' | 'COMPLETED' | 'FAILED' | 'CANCELLED';
  tasks: Task[];
  created_at: string;
  started_at?: string;
  completed_at?: string;
}

export interface Task {
  task_id: string;
  mission_id: string;
  title: string;
  required_action: string;
  status: 'PENDING' | 'ASSIGNED' | 'IN_PROGRESS' | 'COMPLETED' | 'FAILED' | 'ABORTED';
  assigned_device_id?: string;
  sequence: number;
  parameters: Record<string, any>;
  result?: Record<string, any>;
  created_at: string;
  updated_at: string;
}
```

---

## 8. 인증 및 권한 (JWT + RBAC)

### 8.1 로그인

```tsx
// src/pages/Login.tsx

import { useState } from 'react';
import { useAuthStore } from '@/stores/authStore';
import { authService } from '@/services/authService';
import { useNavigate } from 'react-router-dom';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const navigate = useNavigate();
  const { setAuth } = useAuthStore();
  
  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    
    try {
      const { user, token } = await authService.login(email, password);
      setAuth(user, token);
      navigate('/dashboard');
    } catch (err) {
      setError('로그인 실패');
    }
  };
  
  return (
    <form onSubmit={handleLogin} className="space-y-4 max-w-md mx-auto mt-10">
      <input
        type="email"
        placeholder="이메일"
        value={email}
        onChange={e => setEmail(e.target.value)}
        className="w-full px-4 py-2 border rounded"
      />
      <input
        type="password"
        placeholder="비밀번호"
        value={password}
        onChange={e => setPassword(e.target.value)}
        className="w-full px-4 py-2 border rounded"
      />
      {error && <div className="text-red-500">{error}</div>}
      <button type="submit" className="w-full bg-blue-600 text-white py-2 rounded">
        로그인
      </button>
    </form>
  );
}
```

### 8.2 권한 검사 컴포넌트

```tsx
// src/components/common/ProtectedRoute.tsx

import { Navigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';

interface ProtectedRouteProps {
  children: React.ReactNode;
  requiredPermission?: string;
}

export default function ProtectedRoute({
  children,
  requiredPermission
}: ProtectedRouteProps) {
  const { user, hasPermission } = useAuthStore();
  
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  
  if (requiredPermission && !hasPermission(requiredPermission)) {
    return <Navigate to="/forbidden" replace />;
  }
  
  return <>{children}</>;
}
```

---

## 9. 3D 시각화 (Three.js + react-three-fiber)

### 9.1 Scene Canvas

```tsx
// src/components/3d/SceneCanvas.tsx

import React from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, PerspectiveCamera } from '@react-three/drei';
import DeviceModel from './DeviceModel';
import { Device } from '@/types/device';

interface SceneCanvasProps {
  devices: Device[];
}

export default function SceneCanvas({ devices }: SceneCanvasProps) {
  return (
    <Canvas className="w-full h-full">
      <PerspectiveCamera makeDefault position={[0, 30, 50]} />
      <OrbitControls />
      
      {/* 조명 */}
      <ambientLight intensity={0.6} />
      <pointLight position={[10, 10, 10]} intensity={1} />
      
      {/* 바다 배경 */}
      <mesh position={[0, -5, 0]} rotation={[0, 0, 0]}>
        <planeGeometry args={[200, 200]} />
        <meshStandardMaterial color="#1a3a52" />
      </mesh>
      
      {/* Device 모델 렌더링 */}
      {devices.map(device => (
        <DeviceModel key={device.device_id} device={device} />
      ))}
    </Canvas>
  );
}
```

### 9.2 Device 3D 모델

```tsx
// src/components/3d/DeviceModel.tsx

import React from 'react';
import { useFrame } from '@react-three/fiber';
import { useRef } from 'react';
import { Device } from '@/types/device';

interface DeviceModelProps {
  device: Device;
}

export default function DeviceModel({ device }: DeviceModelProps) {
  const groupRef = useRef<THREE.Group>(null);
  
  // Device 위치 (lat/lon → 3D 좌표)
  const x = device.position.lon * 100;
  const z = device.position.lat * 100;
  const y = device.environment_state === 'UNDERWATER' ? -device.depth! : 0;
  
  // Device 색상 (상태에 따라)
  const colorMap = {
    'ONLINE': '#10b981',
    'OFFLINE': '#ef4444',
    'DEGRADED': '#f59e0b',
    'REMOVED': '#6b7280'
  };
  
  return (
    <group ref={groupRef} position={[x, y, z]}>
      {/* Device 본체 */}
      <mesh>
        <boxGeometry args={[5, 3, 8]} />
        <meshStandardMaterial color={colorMap[device.status]} />
      </mesh>
      
      {/* Device 이름 Label */}
      <text
        position={[0, 6, 0]}
        fontSize={2}
        color="#ffffff"
        anchorX="center"
        anchorY="bottom"
      >
        {device.device_id}
      </text>
      
      {/* 신호 강도 표시 */}
      <mesh position={[0, -3, 0]}>
        <cylinderGeometry
          args={[device.signal_strength / 10, device.signal_strength / 10, 1, 32]}
        />
        <meshStandardMaterial color="#3b82f6" transparent opacity={0.5} />
      </mesh>
    </group>
  );
}
```

---

## 10. 성능 최적화

### 10.1 이미지 최적화

```tsx
// Lazy loading
import { lazy, Suspense } from 'react';

const Dashboard = lazy(() => import('@/pages/Dashboard'));

// 사용
<Suspense fallback={<LoadingSpinner />}>
  <Dashboard />
</Suspense>
```

### 10.2 데이터 캐싱 (React Query)

```ts
// 캐시 설정
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5,  // 5분
      cacheTime: 1000 * 60 * 10,  // 10분
      retry: 2
    }
  }
});
```

---

## 11. 배포

### 11.1 빌드

```bash
npm run build
# dist/ 디렉토리에 빌드 결과 생성
```

### 11.2 환경 변수 (.env)

```
REACT_APP_API_URL=http://localhost:9116
REACT_APP_WS_URL=ws://localhost:9116
REACT_APP_SERVER_HOST=localhost
REACT_APP_WS_PORT=9116
```

---

## 12. 참고자료

- [React 공식 문서](https://react.dev)
- [Zustand 문서](https://github.com/pmndrs/zustand)
- [TanStack Query 문서](https://tanstack.com/query/latest)
- [Three.js 문서](https://threejs.org/docs)
- [shadcn/ui 컴포넌트](https://ui.shadcn.com)
