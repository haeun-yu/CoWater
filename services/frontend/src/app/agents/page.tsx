"use client";

import React, { useEffect, useState } from "react";
import { getAgentsApiUrl } from "@/lib/publicUrl";
import {
  useAILogStore,
  isAIAgent,
  type ActivityLogEntry,
} from "@/stores/aiLogStore";
import { useAuthStore } from "@/stores/authStore";
import { useAlertStore } from "@/stores/alertStore";
import { usePlatformStore } from "@/stores/platformStore";
import { formatDistanceToNow, format } from "date-fns";
import { ko } from "date-fns/locale";
import PageHeader from "@/components/ui/PageHeader";
import MetricCard from "@/components/ui/MetricCard";
import EmptyState from "@/components/ui/EmptyState";

const AGENTS_URL = getAgentsApiUrl();
const ROLE_ORDER = { viewer: 0, operator: 1, admin: 2 } as const;

// ── 에이전트 메타 ──────────────────────────────────────────────────────────────

interface PipelineStepDef {
  icon: string;
  title: string;
  sub: string;
  tone?: "idle" | "active" | "alert";
  /** 이 단계가 활성화되는 레벨 조건 (예: "L2+", "L3") */
  level?: string;
}

interface AgentMeta {
  name: string;
  type: "rule" | "ai";
  level: string;
  role: string;
  trigger: string;
  output: string;
  color: string;
  input: string;
  triggeredBy?: string;
  pipeline: PipelineStepDef[];
  /** 분기 경로가 있을 때 (Report Agent 등) */
  routes?: { label: string; steps: PipelineStepDef[] }[];
  subProcess?: { from: string; to: string } | null;
}

const AGENT_META: Record<string, AgentMeta> = {
  "cpa-agent": {
    name: "CPA/TCPA",
    type: "rule",
    level: "L1",
    color: "#2e8dd4",
    role: "충돌 위험 감지",
    trigger: "CPA < 0.5nm & TCPA < 30분 (critical: 0.2nm & 10분)",
    output: "cpa 경보 발생",
    input: "전체 선박 위치·속도·침로 (실시간 AIS 스트림)",
    pipeline: [
      { icon: "◈", title: "데이터 수신", sub: "AIS 위치·속도·침로" },
      { icon: "⊕", title: "쌍방 CPA 계산", sub: "전 선박 조합 벡터 연산", tone: "active" },
      { icon: "◉", title: "임계값 비교", sub: "0.2NM·10min / 0.5NM·30min" },
      { icon: "◎", title: "경보 발행", sub: "cpa Alert" },
    ],
    subProcess: { from: "CPAAgent (critical)", to: "ReportAgent (LLM)" },
  },
  "zone-monitor": {
    name: "Zone Monitor",
    type: "rule",
    level: "L1",
    color: "#22d3ee",
    role: "구역 침입 감시",
    trigger: "선박 위치 ∈ 설정된 금지/주의 구역 경계 내",
    output: "zone_intrusion 경보 발생",
    input: "선박 위치 + 사전 설정된 구역 GeoJSON 경계",
    pipeline: [
      { icon: "◈", title: "위치 수신", sub: "선박 AIS 좌표" },
      { icon: "⊕", title: "구역 로드", sub: "GeoJSON 폴리곤 경계 (5분 갱신)", tone: "active" },
      { icon: "◉", title: "포함 검사", sub: "Point-in-Polygon" },
      { icon: "◎", title: "경보 발행", sub: "zone_intrusion Alert" },
    ],
    subProcess: { from: "ZoneMonitor (critical)", to: "ReportAgent (LLM)" },
  },
  "anomaly-rule": {
    name: "Anomaly Rule",
    type: "rule",
    level: "L1",
    color: "#fbbf24",
    role: "이상 행동 탐지",
    trigger: "AIS 90초 소실 | SOG ≥5kt 급감 | ROT ≥25°/min",
    output: "anomaly / ais_off 경보 발생",
    input: "AIS 위치 보고 스트림 (타임스탬프·속도·회전율)",
    pipeline: [
      { icon: "◈", title: "데이터 수신", sub: "AIS 스트림 (20초 타이머)" },
      { icon: "⊕", title: "상태 캐싱", sub: "속도·선회율·타임스탬프", tone: "active" },
      { icon: "◉", title: "이상 조건 검사", sub: "AIS 90s 소실 · SOG▼5kt · ROT▲25°" },
      { icon: "◎", title: "경보 발행", sub: "anomaly / ais_off Alert" },
    ],
    subProcess: { from: "AnomalyRule", to: "AnomalyAI (LLM)" },
  },
  "anomaly-ai": {
    name: "Anomaly AI",
    type: "ai",
    level: "L2",
    color: "#a78bfa",
    role: "이상 행동 AI 분석",
    trigger: "Anomaly Rule 에이전트의 anomaly/ais_off 경보 수신",
    output: "원인 진단 + 대응 권고",
    input: "Rule 경보 데이터 (선박 ID·마지막 위치·속도·상태) + 이상 유형",
    triggeredBy: "anomaly-rule",
    pipeline: [
      { icon: "◈", title: "경보 수신", sub: "anomaly-rule 트리거" },
      { icon: "⊕", title: "컨텍스트 구성", sub: "경보 + 최근 선박 위치", tone: "active" },
      { icon: "◉", title: "LLM 분석", sub: "Claude / Ollama 추론" },
      { icon: "◎", title: "권고 발행", sub: "compliance Alert (진단+권고)" },
    ],
    subProcess: null,
  },
  "distress-agent": {
    name: "Distress",
    type: "ai",
    level: "L3",
    color: "#f87171",
    role: "조난 상황 대응",
    trigger: "nav_status: not_under_command/aground 또는 ais_off warning (anomaly-rule 경유)",
    output: "distress 경보 + (L2) SAR 권고 + (L3) 자동 통보",
    input: "조난 신호·AIS 소실 경보 + 선박 마지막 위치·상태",
    triggeredBy: "platform_report / anomaly-rule",
    pipeline: [
      {
        icon: "◈",
        title: "조난 감지",
        sub: "nav_status 직접 수신\nor ais_off 경보 경유",
      },
      {
        icon: "⊕",
        title: "조난 여부 판단",
        sub: "not_under_command\naground · AIS 소실",
        tone: "active",
      },
      {
        icon: "◉",
        title: "SAR 권고 생성",
        sub: "LLM 대응 지침 작성",
        level: "L2+",
      },
      {
        icon: "◈",
        title: "자동 통보",
        sub: "Core API → 관계기관",
        tone: "active",
        level: "L3",
      },
      {
        icon: "◎",
        title: "경보 발행",
        sub: "distress Alert\n(critical / warning)",
      },
    ],
    subProcess: { from: "Distress (critical)", to: "ReportAgent (LLM)" },
  },
  "report-agent": {
    name: "Report",
    type: "ai",
    level: "L2",
    color: "#34d399",
    role: "사건 보고서 생성",
    trigger: "① critical 경보 자동 수신  ② 수동 incident_id 요청",
    output: "AI 종합 사건 보고서 (compliance Info)",
    input: "경보 데이터 또는 Incident ID → Core API 조회",
    triggeredBy: "cpa-agent / zone-monitor / distress-agent",
    // 기본 pipeline은 자동 경로
    pipeline: [
      { icon: "◈", title: "Critical 경보 수신", sub: "cpa · distress · zone_intrusion" },
      { icon: "⊕", title: "LLM 보고서 생성", sub: "Claude / Ollama 추론", tone: "active" },
      { icon: "◎", title: "보고서 발행", sub: "compliance Info Alert" },
    ],
    routes: [
      {
        label: "자동 (경보 수신)",
        steps: [
          { icon: "◈", title: "Critical 경보 수신", sub: "cpa · distress · zone_intrusion" },
          { icon: "⊕", title: "LLM 보고서 생성", sub: "Claude / Ollama 추론", tone: "active" },
          { icon: "◎", title: "보고서 발행", sub: "compliance Info Alert" },
        ],
      },
      {
        label: "수동 (Incident ID)",
        steps: [
          { icon: "◈", title: "Incident ID 수신", sub: "POST /report-agent/generate/{id}" },
          { icon: "⊕", title: "Core API 조회", sub: "사건·경보·선박 이력 fetch", tone: "active" },
          { icon: "◉", title: "LLM 보고서 생성", sub: "Claude / Ollama 추론" },
          { icon: "◎", title: "Core API 저장", sub: "보고서 DB 기록" },
        ],
      },
    ],
    subProcess: null,
  },
  "chat-agent": {
    name: "AI 보좌관",
    type: "ai",
    level: "L2",
    color: "#38bdf8",
    role: "운항자와 실시간 대화",
    trigger: "운항자의 직접 질문 (REST POST /chat)",
    output: "상황 요약·위험 분석·대처 방법 등 자연어 답변",
    input: "사용자 메시지 + 현재 선박 상태 캐시 + 활성 경보 목록",
    pipeline: [
      { icon: "◈", title: "메시지 수신", sub: "운항자 질문 입력" },
      {
        icon: "⊕",
        title: "컨텍스트 구성",
        sub: "선박 상태·경보·대화 이력",
        tone: "active",
      },
      { icon: "◉", title: "LLM 추론", sub: "Claude / Ollama 응답 생성" },
      { icon: "◎", title: "답변 반환", sub: "운항자에게 실시간 전달" },
    ],
    subProcess: null,
  },

  // ── 이벤트 드리븐 아키텍처 (Detection Service) ──────────────────────────────
  "detection-cpa": {
    name: "CPA Agent",
    type: "rule",
    level: "L1",
    color: "#2e8dd4",
    role: "Redis 이벤트 기반 CPA 위험 감지",
    trigger: "platform.report.* → CPA/TCPA 계산 → detect.cpa 발행",
    output: "detect.cpa 이벤트 (Redis pub/sub)",
    input: "PlatformReport (위치·속도·침로)",
    pipeline: [
      { icon: "📍", title: "위치 보고 수신", sub: "platform.report.{id}" },
      { icon: "⚡", title: "CPA 계산", sub: "Haversine + 벡터 연산", tone: "active" },
      { icon: "🔔", title: "임계값 확인", sub: "0.2nm/0.5nm, 10min/30min" },
      { icon: "📡", title: "이벤트 발행", sub: "detect.cpa → Redis" },
    ],
    subProcess: { from: "Detection (CPA)", to: "Analysis" },
  },
  "detection-anomaly": {
    name: "Anomaly Agent",
    type: "rule",
    level: "L1",
    color: "#fbbf24",
    role: "Redis 이벤트 기반 이상 행동 감지",
    trigger: "platform.report.* → ROT/Speed/Heading 이상 검사 → detect.anomaly 발행",
    output: "detect.anomaly 이벤트 (Redis pub/sub)",
    input: "PlatformReport (ROT, SOG, Heading 변화)",
    pipeline: [
      { icon: "📍", title: "위치 보고 수신", sub: "platform.report.{id}" },
      { icon: "💾", title: "상태 캐싱", sub: "이전 보고와 비교", tone: "active" },
      { icon: "⚠️", title: "이상 탐지", sub: "ROT ≥20° / SOG ≥5kt / Heading ≥45°" },
      { icon: "📡", title: "이벤트 발행", sub: "detect.anomaly → Redis" },
    ],
    subProcess: { from: "Detection (Anomaly)", to: "Analysis" },
  },
  "detection-zone": {
    name: "Zone Agent",
    type: "rule",
    level: "L1",
    color: "#22d3ee",
    role: "Redis 이벤트 기반 구역 침입 감지",
    trigger: "platform.report.* → Point-in-Polygon → detect.zone 발행",
    output: "detect.zone 이벤트 (Redis pub/sub)",
    input: "PlatformReport + Zone Geometry (PostGIS)",
    pipeline: [
      { icon: "📍", title: "위치 보고 수신", sub: "platform.report.{id}" },
      { icon: "🗺️", title: "구역 로드", sub: "PostGIS geometry 캐시", tone: "active" },
      { icon: "📐", title: "포함 검사", sub: "ST_Contains 공간 쿼리" },
      { icon: "📡", title: "이벤트 발행", sub: "detect.zone → Redis" },
    ],
    subProcess: { from: "Detection (Zone)", to: "Response" },
  },
  "detection-distress": {
    name: "Distress Agent",
    type: "rule",
    level: "L2",
    color: "#f87171",
    role: "Redis 이벤트 기반 조난 신호 감지",
    trigger: "platform.report.* → nav_status 확인 / SART/EPIRB 탐지 → detect.distress 발행",
    output: "detect.distress 이벤트 (Redis pub/sub)",
    input: "PlatformReport (nav_status: not_under_command/aground)",
    pipeline: [
      { icon: "📍", title: "위치 보고 수신", sub: "platform.report.{id}" },
      { icon: "🆘", title: "조난 신호 확인", sub: "nav_status / SART / EPIRB", tone: "active" },
      { icon: "🔍", title: "컨텍스트 수집", sub: "근처 선박·해안 자산" },
      { icon: "📡", title: "이벤트 발행", sub: "detect.distress → Redis" },
    ],
    subProcess: { from: "Detection (Distress)", to: "Analysis" },
  },

  // ── 이벤트 드리븐 아키텍처 (Analysis Service) ──────────────────────────────
  "analysis-anomaly-ai": {
    name: "Analysis Anomaly AI",
    type: "ai",
    level: "L2",
    color: "#a78bfa",
    role: "Redis 이벤트 기반 이상 행동 분석",
    trigger: "detect.anomaly 이벤트 → Claude API 분석 → analyze.anomaly 발행",
    output: "analyze.anomaly 이벤트 (Redis pub/sub)",
    input: "detect.anomaly 페이로드 + API 보강 (선박 이력·근처 자산)",
    triggeredBy: "detection-anomaly",
    pipeline: [
      { icon: "📥", title: "탐지 이벤트 수신", sub: "detect.anomaly" },
      { icon: "🔗", title: "데이터 보강", sub: "Core API: 선박 이력 조회", tone: "active" },
      { icon: "🧠", title: "Claude 분석", sub: "원인 진단 + 신뢰도" },
      { icon: "📡", title: "분석 발행", sub: "analyze.anomaly → Redis" },
    ],
    subProcess: { from: "Analysis (Anomaly AI)", to: "Response" },
  },
  "analysis-report": {
    name: "Analysis Report",
    type: "ai",
    level: "L2",
    color: "#34d399",
    role: "Redis 이벤트 기반 사건 보고서 생성",
    trigger: "detect.* critical 이벤트 → Claude 보고서 작성 → learn.report 발행",
    output: "learn.report 이벤트 (Redis pub/sub)",
    input: "탐지/분석 이벤트 + Core API 종합 정보",
    pipeline: [
      { icon: "📥", title: "Critical 이벤트 수신", sub: "detect.* / analyze.*" },
      { icon: "🔗", title: "종합 정보 수집", sub: "Core API: 경보·선박·구역", tone: "active" },
      { icon: "📝", title: "Claude 보고서 생성", sub: "상황·원인·권고" },
      { icon: "📡", title: "보고서 발행", sub: "learn.report → Redis" },
    ],
    subProcess: null,
  },

  // ── 이벤트 드리븐 아키텍처 (Response Service) ──────────────────────────────
  "response-alert-creator": {
    name: "Response Alert Creator",
    type: "rule",
    level: "L1",
    color: "#ec4899",
    role: "Redis 이벤트 기반 경보 자동 생성",
    trigger: "analyze.* 이벤트 → Core API Alert 생성 → respond.alert 발행",
    output: "respond.alert 이벤트 (Redis pub/sub)",
    input: "analyze.anomaly / analyze.report 페이로드",
    triggeredBy: "analysis-anomaly-ai",
    pipeline: [
      { icon: "📥", title: "분석 이벤트 수신", sub: "analyze.anomaly" },
      { icon: "⚡", title: "Alert 생성", sub: "Core API POST /alerts", tone: "active" },
      { icon: "📋", title: "메타데이터 설정", sub: "severity·recommendation" },
      { icon: "📡", title: "응답 이벤트 발행", sub: "respond.alert → Redis" },
    ],
    subProcess: null,
  },

  // ── 이벤트 드리븐 아키텍처 (Supervision Service) ──────────────────────────────
  "supervision-supervisor": {
    name: "Supervision Supervisor",
    type: "rule",
    level: "L1",
    color: "#6366f1",
    role: "Redis 이벤트 기반 에이전트 헬스 모니터링",
    trigger: "system.heartbeat.* 수신 → 타임아웃 확인 → system.alert 발행",
    output: "system.alert 이벤트 (Redis pub/sub)",
    input: "system.heartbeat.{service} (에이전트 생존 신호)",
    pipeline: [
      { icon: "💓", title: "하트비트 수신", sub: "system.heartbeat.{service}" },
      { icon: "⏱️", title: "타임아웃 확인", sub: "60초 이상 미수신", tone: "active" },
      { icon: "🚨", title: "헬스 체크", sub: "서비스 상태 판단" },
      { icon: "📡", title: "경고 발행", sub: "system.alert → Redis" },
    ],
    subProcess: null,
  },

  // ── 이벤트 드리븐 아키텍처 (Learning Service) ──────────────────────────────
  "learning-agent": {
    name: "Learning Agent",
    type: "ai",
    level: "L2",
    color: "#8b5cf6",
    role: "Redis 이벤트 기반 거짓 경보율 추적 및 규칙 개선",
    trigger: "system.ack.* (사용자 피드백) → 거짓 경보율 계산 → learn.feedback 발행",
    output: "learn.feedback 이벤트 (Redis pub/sub)",
    input: "system.ack.{alert_id} (acknowledged/resolved 피드백)",
    pipeline: [
      { icon: "👤", title: "피드백 수신", sub: "system.ack.{alert_id}" },
      { icon: "📊", title: "거짓 경보율 계산", sub: "Redis FP_FEEDBACK 통계", tone: "active" },
      { icon: "💡", title: "규칙 개선 제안", sub: "임계값 조정 권고" },
      { icon: "📡", title: "학습 이벤트 발행", sub: "learn.feedback → Redis" },
    ],
    subProcess: null,
  },
};

// ── 심각도 ────────────────────────────────────────────────────────────────────

const SEV = {
  critical: {
    border: "border-l-red-500",
    headerBg: "bg-red-950/30",
    text: "text-red-400",
    badge: "bg-red-900/50 text-red-300 border border-red-700/50",
    dot: "bg-red-500",
    label: "위험",
  },
  warning: {
    border: "border-l-amber-500",
    headerBg: "bg-amber-950/20",
    text: "text-amber-400",
    badge: "bg-amber-900/50 text-amber-300 border border-amber-700/50",
    dot: "bg-amber-500",
    label: "주의",
  },
  info: {
    border: "border-l-blue-500",
    headerBg: "",
    text: "text-blue-400",
    badge: "bg-blue-900/50 text-blue-300 border border-blue-700/50",
    dot: "bg-blue-500",
    label: "정보",
  },
} as const;

const ALERT_TYPE_KR: Record<string, string> = {
  cpa: "충돌 위험",
  zone_intrusion: "구역 침입",
  zone_exit: "구역 이탈",
  anomaly: "이상 행동",
  ais_off: "AIS 소실",
  ais_recovered: "AIS 복구",
  distress: "조난",
  compliance: "상황 보고",
};

// ── Agent Status (API 응답) ────────────────────────────────────────────────────

interface AgentStatus {
  agent_id: string;
  name: string;
  type: string;
  level: string;
  enabled: boolean;
  failure_count?: number;
  last_error?: string | null;
  model_name?: string;
  config?: Record<string, unknown>;
}

// ── 페이지 ────────────────────────────────────────────────────────────────────

export default function AgentsPage() {
  const logs = useAILogStore((s) => s.logs);
  const clearLogs = useAILogStore((s) => s.clear);
  const alerts = useAlertStore((s) => s.alerts);
  const platforms = usePlatformStore((s) => s.platforms);

  const [agentFilter, setAgentFilter] = useState<string>("all");
  const [typeFilter, setTypeFilter] = useState<"all" | "rule" | "ai">("all");
  const [expandedLog, setExpandedLog] = useState<string | null>(null);
  const [statuses, setStatuses] = useState<AgentStatus[]>([]);
  const [updating, setUpdating] = useState<string | null>(null);
  const [apiStatus, setApiStatus] = useState<"ok" | "fallback" | "unknown">("unknown");
  const [modelEditing, setModelEditing] = useState<string | null>(null);
  const [modelInput, setModelInput] = useState<string>("");

  // LLM 전역 설정
  const [llmConfig, setLlmConfig] = useState<{ backend: string; model: string } | null>(null);
  const [llmEditing, setLlmEditing] = useState(false);
  const [llmBackendInput, setLlmBackendInput] = useState<string>("");
  const [llmModelInput, setLlmModelInput] = useState<string>("");
  const [llmUpdating, setLlmUpdating] = useState(false);

  // 에이전트 config 편집
  const [configEditing, setConfigEditing] = useState<string | null>(null);
  const [configInput, setConfigInput] = useState<string>("");
  const [configError, setConfigError] = useState<string | null>(null);

  // 보고서 생성
  const [reportIncidentId, setReportIncidentId] = useState<string>("");
  const [reportGenerating, setReportGenerating] = useState(false);
  const [reportResult, setReportResult] = useState<{ alert_id: string; report: string } | null>(null);
  const [reportError, setReportError] = useState<string | null>(null);
  const [reportExpanded, setReportExpanded] = useState(false);

  const token = useAuthStore((s) => s.token);
  const role = useAuthStore((s) => s.role);
  const canManageAgents = !!token && !!role && ROLE_ORDER[role] >= ROLE_ORDER.admin;

  useEffect(() => {
    fetch(`${AGENTS_URL}/agents`)
      .then((r) => r.json())
      .then((s: AgentStatus[]) => setStatuses(s))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (logs.some((l) => l.model?.includes("fallback"))) setApiStatus("fallback");
    else if (logs.some((l) => l.model && !l.model.includes("fallback") && isAIAgent(l.agent_id)))
      setApiStatus("ok");
  }, [logs]);

  useEffect(() => {
    fetch(`${AGENTS_URL}/llm`)
      .then((r) => r.json())
      .then((data: { backend: string; model: string }) => setLlmConfig(data))
      .catch(() => {});
  }, []);

  async function toggleAgent(id: string, enable: boolean) {
    if (!token || !canManageAgents) return;
    setUpdating(id);
    try {
      await fetch(`${AGENTS_URL}/agents/${id}/${enable ? "enable" : "disable"}`, {
        method: "PATCH",
        headers: { Authorization: `Bearer ${token}` },
      });
      setStatuses((p) => p.map((a) => (a.agent_id === id ? { ...a, enabled: enable } : a)));
    } finally {
      setUpdating(null);
    }
  }

  async function setLevel(id: string, level: string) {
    if (!token || !canManageAgents) return;
    setUpdating(id);
    try {
      await fetch(`${AGENTS_URL}/agents/${id}/level`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ level }),
      });
      setStatuses((p) => p.map((a) => (a.agent_id === id ? { ...a, level } : a)));
    } finally {
      setUpdating(null);
    }
  }

  async function applyModel(id: string, model: string) {
    if (!token || !canManageAgents) return;
    const trimmed = model.trim();
    if (!trimmed) return;
    setUpdating(id);
    try {
      const res = await fetch(`${AGENTS_URL}/agents/${id}/model`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ model: trimmed }),
      });
      if (res.ok) {
        const data = await res.json();
        setStatuses((p) =>
          p.map((a) => (a.agent_id === id ? { ...a, model_name: data.model_name } : a)),
        );
        setModelEditing(null);
      }
    } finally {
      setUpdating(null);
    }
  }

  async function applyConfig(id: string) {
    if (!token || !canManageAgents) return;
    setConfigError(null);
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(configInput);
    } catch {
      setConfigError("JSON 형식이 올바르지 않습니다");
      return;
    }
    setUpdating(id);
    try {
      const res = await fetch(`${AGENTS_URL}/agents/${id}/config`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify(parsed),
      });
      if (res.ok) {
        const data = await res.json();
        setStatuses((p) =>
          p.map((a) => (a.agent_id === id ? { ...a, config: data.config } : a)),
        );
        setConfigEditing(null);
        setConfigInput("");
      }
    } finally {
      setUpdating(null);
    }
  }

  async function applyLLM() {
    if (!token || !canManageAgents) return;
    const backend = llmBackendInput.trim();
    const model = llmModelInput.trim();
    if (!backend || !model) return;
    setLlmUpdating(true);
    try {
      const res = await fetch(`${AGENTS_URL}/llm`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ backend, model }),
      });
      if (res.ok) {
        const data = await res.json();
        setLlmConfig({ backend: data.backend, model: data.model });
        setLlmEditing(false);
        setLlmBackendInput("");
        setLlmModelInput("");
      }
    } finally {
      setLlmUpdating(false);
    }
  }

  async function generateReport() {
    const id = reportIncidentId.trim();
    if (!id) return;
    setReportGenerating(true);
    setReportError(null);
    setReportResult(null);
    try {
      const res = await fetch(`${AGENTS_URL}/agents/report-agent/generate/${encodeURIComponent(id)}`, {
        method: "POST",
      });
      if (!res.ok) {
        setReportError(`요청 실패: ${res.status}`);
        return;
      }
      const data = await res.json();
      setReportResult(data);
      setReportExpanded(true);
    } catch {
      setReportError("네트워크 오류가 발생했습니다");
    } finally {
      setReportGenerating(false);
    }
  }

  function getPlatformName(id: string) {
    const p = platforms[id];
    return p?.name && p.name !== p.platform_id ? p.name : id.replace(/^MMSI-/, "");
  }

  function logCount(id: string) {
    return logs.filter((l) => l.agent_id === id).length;
  }

  const activeAlertAgents = new Set(
    alerts.filter((a) => a.status === "new").map((a) => a.generated_by),
  );

  const filteredLogs = logs
    .filter((l) => agentFilter === "all" || l.agent_id === agentFilter)
    .filter((l) => typeFilter === "all" || l.agent_type === typeFilter);

  const criticalCount = alerts.filter((a) => a.status === "new" && a.severity === "critical").length;
  const warningCount = alerts.filter((a) => a.status === "new" && a.severity === "warning").length;
  const aiCount = logs.filter((l) => isAIAgent(l.agent_id)).length;
  const ruleCount = logs.length - aiCount;

  function agentsOf(agentType: "rule" | "ai"): AgentStatus[] {
    const live = statuses.filter((a) => a.type === agentType);
    if (live.length > 0) return live;
    return Object.entries(AGENT_META)
      .filter(([, m]) => m.type === agentType)
      .map(([id, m]) => ({ agent_id: id, name: m.name, type: agentType, level: m.level, enabled: true }));
  }

  const ruleAgents = agentsOf("rule");
  const aiAgents = agentsOf("ai");

  const focusAgentId =
    agentFilter === "all" ? (filteredLogs[0]?.agent_id ?? "cpa-agent") : agentFilter;
  const focusMeta = AGENT_META[focusAgentId] ?? AGENT_META["cpa-agent"];
  const focusStatus = statuses.find((s) => s.agent_id === focusAgentId);

  // 에이전트별 이벤트 수 (바 차트용)
  const allAgentIds = [...ruleAgents, ...aiAgents].map((a) => a.agent_id);
  const maxCount = Math.max(1, ...allAgentIds.map((id) => logCount(id)));

  return (
    <div className="page-shell bg-slate-950 text-slate-200">
      <PageHeader
        title="통합 에이전트 관제"
        stats={[
          <MetricCard key="tracked" label="관제 중" value={`${Object.keys(platforms).length}척`} valueClassName="text-xl" className="bg-slate-900/70" />,
          <MetricCard key="rule" label="Rule 이벤트" value={ruleCount} tone="info" valueClassName="text-xl" className="bg-slate-900/70" />,
          <MetricCard key="ai" label="AI 이벤트" value={aiCount} valueClassName="text-xl" className="bg-slate-900/70" />,
          criticalCount > 0 ? <MetricCard key="critical" label="위험 경보" value={criticalCount} tone="critical" valueClassName="text-xl" className="bg-slate-900/70" /> : null,
          warningCount > 0 ? <MetricCard key="warning" label="주의 경보" value={warningCount} tone="warning" valueClassName="text-xl" className="bg-slate-900/70" /> : null,
        ]}
      />

      <main className="grid flex-1 min-h-0 grid-cols-1 overflow-auto xl:grid-cols-[260px_minmax(0,1fr)_440px] xl:overflow-hidden">

        {/* ── 왼쪽: 에이전트 목록 + 컨트롤 ───────────────────────────────────── */}
        <section className="border-r border-slate-800/80 bg-slate-950/55 flex min-h-[260px] flex-col overflow-hidden xl:min-h-0">
          <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between">
            <span className="text-xs text-slate-400 uppercase tracking-widest font-bold">
              Agent Orchestrator
            </span>
            {apiStatus !== "unknown" && (
              <span className={`text-xs px-1.5 py-0.5 rounded border ${
                apiStatus === "ok"
                  ? "text-green-400 border-green-700/40 bg-green-950/30"
                  : "text-amber-400 border-amber-700/40 bg-amber-950/30"
              }`}>
                {apiStatus === "ok" ? "LLM ✓" : "Fallback"}
              </span>
            )}
          </div>

          <div className="flex-1 overflow-auto">
            {/* LLM 전역 설정 */}
            {llmConfig && (
              <div className="px-3 pt-3 pb-2 border-b border-slate-800">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs text-violet-400 font-bold uppercase tracking-wider">
                    LLM 설정
                  </span>
                  {!llmEditing && canManageAgents && (
                    <button
                      onClick={() => {
                        setLlmEditing(true);
                        setLlmBackendInput(llmConfig.backend);
                        setLlmModelInput(llmConfig.model);
                      }}
                      className="text-xs text-ocean-400 hover:text-ocean-300"
                    >
                      변경
                    </button>
                  )}
                </div>
                {llmEditing ? (
                  <div className="space-y-2">
                    <select
                      value={llmBackendInput}
                      onChange={(e) => setLlmBackendInput(e.target.value)}
                      className="w-full text-xs bg-slate-950 border border-slate-700 rounded px-2 py-1 text-slate-200 focus:outline-none focus:border-ocean-600"
                    >
                      <option value="claude">Claude (Anthropic)</option>
                      <option value="ollama">Ollama (로컬)</option>
                      <option value="vllm">vLLM (고성능)</option>
                    </select>
                    <input
                      type="text"
                      value={llmModelInput}
                      onChange={(e) => setLlmModelInput(e.target.value)}
                      placeholder="모델명 입력"
                      className="w-full text-xs bg-slate-950 border border-slate-700 rounded px-2 py-1 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-ocean-600 font-mono"
                    />
                    <div className="flex gap-1">
                      <button
                        onClick={() => applyLLM()}
                        disabled={llmUpdating || !llmBackendInput.trim() || !llmModelInput.trim()}
                        className="flex-1 text-xs py-1 rounded bg-ocean-700 hover:bg-ocean-600 text-white disabled:opacity-40 font-medium"
                      >
                        {llmUpdating ? "적용 중…" : "적용"}
                      </button>
                      <button
                        onClick={() => setLlmEditing(false)}
                        className="flex-1 text-xs py-1 rounded border border-slate-700 text-slate-400 hover:border-slate-500 font-medium"
                      >
                        취소
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="text-xs text-slate-300 space-y-0.5">
                    <div>
                      <span className="text-slate-500">Backend:</span> <span className="text-violet-300 font-mono">{llmConfig.backend}</span>
                    </div>
                    <div>
                      <span className="text-slate-500">Model:</span> <span className="text-violet-300 font-mono">{llmConfig.model}</span>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Rule 에이전트 */}
            <div className="px-3 pt-3 pb-1">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-blue-400 font-bold uppercase tracking-wider">
                  Rule Based
                </span>
                <span className="text-xs text-slate-500">
                  {ruleAgents.filter((a) => a.enabled).length}/{ruleAgents.length} 활성
                </span>
              </div>
              <div className="space-y-1">
                {ruleAgents.map((a) => (
                  <AgentControlRow
                    key={a.agent_id}
                    agent={a}
                    count={logCount(a.agent_id)}
                    maxCount={maxCount}
                    isActive={activeAlertAgents.has(a.agent_id)}
                    isUpdating={updating === a.agent_id}
                    canManage={canManageAgents}
                    selected={agentFilter === a.agent_id}
                    onSelect={() => {
                      setAgentFilter(a.agent_id);
                      setTypeFilter("rule");
                    }}
                    onToggle={toggleAgent}
                    onLevel={setLevel}
                  />
                ))}
              </div>
            </div>

            <div className="my-2 mx-3 border-t border-slate-800/60" />

            {/* AI 에이전트 */}
            <div className="px-3 pb-3">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-violet-400 font-bold uppercase tracking-wider">
                  AI Based
                </span>
                <span className="text-xs text-slate-500">
                  {aiAgents.filter((a) => a.enabled).length}/{aiAgents.length} 준비
                </span>
              </div>
              <div className="space-y-1">
                {aiAgents.map((a) => (
                  <AgentControlRow
                    key={a.agent_id}
                    agent={a}
                    count={logCount(a.agent_id)}
                    maxCount={maxCount}
                    isActive={activeAlertAgents.has(a.agent_id)}
                    isUpdating={updating === a.agent_id}
                    canManage={canManageAgents}
                    selected={agentFilter === a.agent_id}
                    onSelect={() => {
                      setAgentFilter(a.agent_id);
                      setTypeFilter("ai");
                    }}
                    onToggle={toggleAgent}
                    onLevel={setLevel}
                  />
                ))}
              </div>
            </div>
          </div>

          <div className="px-3 pb-3">
            <button
              onClick={() => { setAgentFilter("all"); setTypeFilter("all"); }}
              className={`w-full text-xs py-1.5 rounded border transition-colors ${
                agentFilter === "all"
                  ? "border-slate-600 text-white bg-slate-800"
                  : "border-slate-700 text-slate-400 hover:border-slate-500"
              }`}
            >
              전체 이벤트 보기
            </button>
          </div>
        </section>

        {/* ── 가운데: 파이프라인 흐름 + 이벤트 빈도 ──────────────────────────── */}
        <section className="border-r border-slate-800/80 bg-slate-950/35 flex min-h-[320px] flex-col overflow-hidden xl:min-h-0">
          <div className="px-5 py-3 border-b border-slate-800 flex items-center justify-between">
            <div>
              <h2 className="text-sm font-bold text-white tracking-tight">
                Agent Pipeline Flow
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                {focusMeta.name}: {focusMeta.role}
              </p>
            </div>
            {/* 선택된 에이전트 실제 상태 */}
            {focusStatus && (
              <div className="flex items-center gap-2 text-xs">
                <span className={`w-1.5 h-1.5 rounded-full ${
                  focusStatus.enabled ? "bg-green-400" : "bg-slate-600"
                }`} />
                <span className={focusStatus.enabled ? "text-green-400" : "text-slate-500"}>
                  {focusStatus.enabled ? "활성" : "비활성"}
                </span>
                <span className="text-slate-600">·</span>
                <span className="text-slate-400 font-mono">{focusStatus.level}</span>
                {(focusStatus.failure_count ?? 0) > 0 && (
                  <>
                    <span className="text-slate-600">·</span>
                    <span className="text-red-400">오류 {focusStatus.failure_count}회</span>
                  </>
                )}
              </div>
            )}
          </div>

          {/* 파이프라인 스텝 */}
          <div className="h-40 overflow-y-auto p-3 bg-[radial-gradient(#1e293b_1px,transparent_1px)] [background-size:24px_24px]">
            <HorizontalPipeline
              steps={focusMeta.pipeline}
              routes={focusMeta.routes}
              criticalCount={criticalCount}
              warningCount={warningCount}
              active={logs.length > 0}
              agentLevel={focusStatus?.level ?? focusMeta.level}
            />
          </div>

          {/* 하단: Sub-Process + 이벤트 빈도 차트 */}
          <div className="flex-1 border-t border-slate-800 bg-slate-900/30 px-5 py-3 flex gap-4 overflow-auto">
            {/* Sub-Process Trigger */}
            <div className="flex-none min-w-0">
              <div className="text-xs text-slate-500 font-bold uppercase mb-2">
                Sub-Process Trigger
              </div>
              {focusMeta.subProcess ? (
                <div className="flex items-center gap-2 text-sm font-mono">
                  <span className="px-2.5 py-1.5 bg-slate-950 border border-slate-800 rounded text-slate-300">
                    {focusMeta.subProcess.from}
                  </span>
                  <span className="text-slate-600">→</span>
                  <span className="px-2.5 py-1.5 bg-violet-600/20 border border-violet-500/40 rounded text-violet-400 font-bold">
                    {focusMeta.subProcess.to}
                  </span>
                </div>
              ) : (
                <div className="text-sm text-slate-600 italic font-mono">독립 실행 에이전트</div>
              )}
            </div>

            {/* 에이전트별 이벤트 빈도 미니 차트 */}
            <div className="flex-1 min-w-0">
              <div className="text-xs text-slate-500 font-bold uppercase mb-2">
                이벤트 처리 현황
              </div>
              <div className="flex items-end gap-1.5 h-10">
                {[...ruleAgents, ...aiAgents].map((a) => {
                  const count = logCount(a.agent_id);
                  const pct = maxCount > 0 ? (count / maxCount) * 100 : 0;
                  const meta = AGENT_META[a.agent_id];
                  const color = meta?.color ?? "#4a7a9b";
                  const isSelected = agentFilter === a.agent_id;
                  return (
                    <button
                      key={a.agent_id}
                      onClick={() => {
                        setAgentFilter(a.agent_id);
                        setTypeFilter(a.type as "rule" | "ai");
                      }}
                      title={`${meta?.name ?? a.agent_id}: ${count}건`}
                      className="flex-1 flex flex-col items-center gap-0.5 group"
                    >
                      <div className="text-xs font-mono text-slate-500 group-hover:text-slate-300">
                        {count > 0 ? count : ""}
                      </div>
                      <div className="w-full relative" style={{ height: 24 }}>
                        <div
                          className="absolute bottom-0 w-full rounded-t transition-all"
                          style={{
                            height: `${Math.max(pct, count > 0 ? 15 : 4)}%`,
                            background: a.enabled ? color : "#334155",
                            opacity: isSelected ? 1 : 0.5,
                            outline: isSelected ? `1px solid ${color}` : "none",
                          }}
                        />
                      </div>
                      <div
                        className="text-xs truncate w-full text-center"
                        style={{ color: a.enabled ? color : "#4a5568", opacity: 0.8 }}
                      >
                        {meta?.name?.split(" ")[0] ?? a.agent_id}
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        </section>

        {/* ── 오른쪽: 에이전트 상세 + 이벤트 로그 ───────────────────────────── */}
        <section className="bg-slate-950 flex min-h-[320px] flex-col overflow-hidden xl:min-h-0">
          <div className="p-4 border-b border-slate-800 space-y-3">
            {/* 에이전트 요약 */}
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <h3 className="text-sm font-bold text-white truncate">
                  {focusMeta.name}
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">{focusMeta.role}</p>
              </div>
              <button
                onClick={clearLogs}
                className="text-xs px-2 py-1 rounded border border-slate-700 text-slate-400 hover:border-red-500/60 hover:text-red-300 flex-shrink-0"
              >
                로그 초기화
              </button>
            </div>

            {/* 실제 에이전트 상태 */}
            {focusStatus ? (
              <div className="grid grid-cols-2 gap-2">
                <InfoCell
                  label="상태"
                  value={focusStatus.enabled ? "활성 (Enabled)" : "비활성 (Disabled)"}
                  color={focusStatus.enabled ? "text-green-400" : "text-slate-500"}
                />
                <InfoCell label="자율성 레벨" value={focusStatus.level} color="text-blue-400" />
                <InfoCell
                  label="오류 횟수"
                  value={`${focusStatus.failure_count ?? 0}회`}
                  color={(focusStatus.failure_count ?? 0) > 0 ? "text-red-400" : "text-slate-500"}
                />
                <InfoCell
                  label="처리 건수"
                  value={`${logCount(focusAgentId)}건`}
                  color="text-ocean-300"
                />
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-2">
                <InfoCell label="타입" value={focusMeta.type === "ai" ? "AI 에이전트" : "Rule 에이전트"} />
                <InfoCell label="기본 레벨" value={focusMeta.level} color="text-blue-400" />
              </div>
            )}

            {/* AI 에이전트 모델 표시 + 변경 */}
            {focusMeta.type === "ai" && (
              <div className="bg-slate-900/50 border border-slate-800 rounded p-2.5">
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-xs text-slate-500 uppercase font-bold">LLM 모델</span>
                  {modelEditing === focusAgentId ? (
                    <button
                      onClick={() => setModelEditing(null)}
                      className="text-xs text-slate-500 hover:text-slate-300"
                    >
                      취소
                    </button>
                  ) : (
                    canManageAgents ? (
                      <button
                        onClick={() => {
                          setModelEditing(focusAgentId);
                          setModelInput(focusStatus?.model_name?.split("/")[1] ?? "");
                        }}
                        className="text-xs text-ocean-400 hover:text-ocean-300"
                      >
                        변경
                      </button>
                    ) : (
                      <span className="text-[10px] text-slate-600">admin 필요</span>
                    )
                  )}
                </div>
                {modelEditing === focusAgentId ? (
                  <div className="flex gap-1.5">
                    <input
                      value={modelInput}
                      onChange={(e) => setModelInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") applyModel(focusAgentId, modelInput);
                        if (e.key === "Escape") setModelEditing(null);
                      }}
                      placeholder="예: qwen2.5:0.5b"
                      className="flex-1 text-xs bg-slate-950 border border-slate-700 rounded px-2 py-1 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-ocean-600 font-mono"
                      autoFocus
                    />
                    <button
                      onClick={() => applyModel(focusAgentId, modelInput)}
                      disabled={updating === focusAgentId || !modelInput.trim()}
                      className="text-xs px-2.5 py-1 rounded bg-ocean-700 hover:bg-ocean-600 text-white disabled:opacity-40"
                    >
                      적용
                    </button>
                  </div>
                ) : (
                  <span className="text-sm font-mono text-violet-300">
                    {focusStatus?.model_name ?? "—"}
                  </span>
                )}
              </div>
            )}

            {/* 에이전트 Config 편집 */}
            <div className="bg-slate-900/50 border border-slate-800 rounded p-2.5">
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-xs text-slate-500 uppercase font-bold">Config</span>
                {configEditing === focusAgentId ? (
                  <button
                    onClick={() => { setConfigEditing(null); setConfigError(null); }}
                    className="text-xs text-slate-500 hover:text-slate-300"
                  >
                    취소
                  </button>
                ) : (
                  canManageAgents ? (
                    <button
                      onClick={() => {
                        setConfigEditing(focusAgentId);
                        const currentConfig = focusStatus?.config ?? {};
                        setConfigInput(JSON.stringify(currentConfig, null, 2));
                        setConfigError(null);
                      }}
                      className="text-xs text-ocean-400 hover:text-ocean-300"
                    >
                      편집
                    </button>
                  ) : (
                    <span className="text-[10px] text-slate-600">admin 필요</span>
                  )
                )}
              </div>

              {configEditing === focusAgentId ? (
                <div className="space-y-1.5">
                  <textarea
                    value={configInput}
                    onChange={(e) => setConfigInput(e.target.value)}
                    rows={5}
                    placeholder='{"key": "value"}'
                    className="w-full text-xs bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-ocean-600 font-mono resize-none"
                  />
                  {configError && (
                    <div className="text-xs text-red-400">{configError}</div>
                  )}
                  <button
                    onClick={() => applyConfig(focusAgentId)}
                    disabled={updating === focusAgentId || !configInput.trim()}
                    className="w-full text-xs py-1 rounded bg-ocean-700 hover:bg-ocean-600 text-white disabled:opacity-40"
                  >
                    적용
                  </button>
                </div>
              ) : (
                <div className="font-mono text-xs text-slate-400">
                  {focusStatus?.config && Object.keys(focusStatus.config).length > 0 ? (
                    <pre className="whitespace-pre-wrap break-all text-[10px]">
                      {JSON.stringify(focusStatus.config, null, 2)}
                    </pre>
                  ) : (
                    <span className="text-slate-600 italic">설정 없음</span>
                  )}
                </div>
              )}
            </div>

            {/* 마지막 오류 */}
            {focusStatus?.last_error && (
              <div className="px-2.5 py-2 bg-red-950/30 border border-red-800/40 rounded text-xs text-red-300 font-mono leading-snug line-clamp-2">
                {focusStatus.last_error}
              </div>
            )}

            {/* fallback 경고 */}
            {apiStatus === "fallback" && (
              <div className="px-2.5 py-2 bg-amber-500/10 border border-amber-500/40 rounded text-xs text-amber-300">
                ANTHROPIC_API_KEY 미설정 — fallback 권고가 생성 중입니다.
              </div>
            )}

            {/* 트리거 / 입력 / 출력 요약 */}
            <div className="space-y-1.5">
              <FlowRow icon="⚡" label="트리거" value={focusMeta.trigger} color="text-yellow-400" />
              <FlowRow icon="→" label="입력" value={focusMeta.input} color="text-slate-400" />
              <FlowRow icon="⬡" label="출력" value={focusMeta.output} color="text-green-400" />
            </div>

            {/* 보고서 생성 — report-agent 선택 시만 표시 */}
            {focusAgentId === "report-agent" && (
              <div className="bg-slate-900/50 border border-slate-800 rounded p-2.5 space-y-2">
                <div className="text-xs text-slate-500 uppercase font-bold">Alert 기반 보고서</div>
                <div className="flex gap-1.5">
                  <input
                    value={reportIncidentId}
                    onChange={(e) => setReportIncidentId(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") generateReport(); }}
                    placeholder="Alert ID 입력"
                    className="flex-1 text-xs bg-slate-950 border border-slate-700 rounded px-2 py-1 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-ocean-600 font-mono"
                  />
                  <button
                    onClick={generateReport}
                    disabled={reportGenerating || !reportIncidentId.trim()}
                    className="text-xs px-3 py-1 rounded bg-emerald-700/70 hover:bg-emerald-700 text-white disabled:opacity-40 flex-shrink-0"
                  >
                    {reportGenerating ? "생성 중…" : "생성"}
                  </button>
                </div>

                {reportError && (
                  <div className="text-xs text-red-400">{reportError}</div>
                )}

                {reportResult && (
                  <div>
                    <button
                      onClick={() => setReportExpanded(!reportExpanded)}
                      className="w-full flex items-center justify-between text-xs text-emerald-400 hover:text-emerald-300 py-1"
                    >
                      <span>보고서: {reportResult.alert_id}</span>
                      <span>{reportExpanded ? "▲ 접기" : "▼ 펼치기"}</span>
                    </button>
                    {reportExpanded && (
                      <pre className="mt-1 text-xs text-slate-300 bg-slate-950 border border-slate-700 rounded p-2.5 whitespace-pre-wrap break-words max-h-64 overflow-y-auto font-mono leading-relaxed">
                        {reportResult.report}
                      </pre>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* 로그 필터 */}
            <div className="flex items-center gap-1.5 flex-wrap pt-0.5">
              {(["all", "rule", "ai"] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setTypeFilter(t)}
                  className={`text-xs px-2.5 py-1 rounded border transition-colors ${
                    typeFilter === t
                      ? "bg-ocean-800 text-white border-ocean-600"
                      : "border-slate-700 text-slate-400 hover:border-slate-500"
                  }`}
                >
                  {t === "all" ? "전체" : t.toUpperCase()}
                </button>
              ))}
              <span className="ml-auto text-xs text-slate-600">
                {filteredLogs.length}건
              </span>
            </div>
          </div>

          {/* 이벤트 로그 */}
          <div className="flex-1 overflow-auto p-3 space-y-2">
            {filteredLogs.length === 0 ? (
              <div className="h-full flex items-center justify-center">
                <div className="w-full max-w-sm">
                  <EmptyState title="처리 기록 없음" description={agentFilter !== "all" ? `${focusMeta.name}의 이벤트가 없습니다` : "에이전트 이벤트를 기다리는 중"} />
                </div>
              </div>
            ) : (
              filteredLogs.map((log) => (
                <LogCard
                  key={log.id}
                  log={log}
                  expanded={expandedLog === log.id}
                  onToggle={() => setExpandedLog(expandedLog === log.id ? null : log.id)}
                  getPlatformName={getPlatformName}
                />
              ))
            )}
          </div>
        </section>
      </main>
    </div>
  );
}

// ── 에이전트 컨트롤 행 (왼쪽 패널) ──────────────────────────────────────────

function AgentControlRow({
  agent,
  count,
  maxCount,
  isActive,
  isUpdating,
  canManage,
  selected,
  onSelect,
  onToggle,
  onLevel,
}: {
  agent: AgentStatus;
  count: number;
  maxCount: number;
  isActive: boolean;
  isUpdating: boolean;
  canManage: boolean;
  selected: boolean;
  onSelect: () => void;
  onToggle: (id: string, e: boolean) => void;
  onLevel: (id: string, l: string) => void;
}) {
  const meta = AGENT_META[agent.agent_id];
  const color = meta?.color ?? "#7ab8d9";
  const isAI = agent.type === "ai";
  const barPct = maxCount > 0 ? (count / maxCount) * 100 : 0;

  return (
    <div
      className={`rounded border transition-colors ${
        selected
          ? isAI
            ? "bg-violet-600/10 border-violet-500/30"
            : "bg-blue-600/10 border-blue-500/30"
          : "bg-slate-900/40 border-slate-800/60 hover:border-slate-700"
      } ${!agent.enabled ? "opacity-50" : ""}`}
    >
      {/* 메인 행 */}
      <div className="flex items-center gap-1.5 px-2.5 py-2">
        {/* 상태 도트 */}
        <span
          className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
            !agent.enabled ? "bg-slate-700"
            : isActive ? (isAI ? "bg-violet-400 animate-pulse" : "bg-blue-400 animate-pulse")
            : "bg-slate-600"
          }`}
        />

        {/* 이름 (클릭 → 필터) */}
        <button
          className="flex-1 min-w-0 text-left text-sm font-semibold truncate"
          style={{ color: agent.enabled ? color : "#64748b" }}
          onClick={onSelect}
        >
          {meta?.name ?? agent.agent_id}
        </button>

        {/* 이벤트 수 */}
        {count > 0 && (
          <span className="text-xs font-mono text-slate-400 flex-shrink-0">
            {count}
          </span>
        )}

        {/* 레벨 */}
        {isAI ? (
          <select
            value={agent.level}
            onChange={(e) => onLevel(agent.agent_id, e.target.value)}
            disabled={isUpdating || !agent.enabled || !canManage}
            onClick={(e) => e.stopPropagation()}
            className="text-xs bg-slate-900 border border-slate-700 text-slate-300 rounded px-1 py-0.5 flex-shrink-0 disabled:opacity-40 cursor-pointer"
          >
            <option value="L1">L1</option>
            <option value="L2">L2</option>
            <option value="L3">L3</option>
          </select>
        ) : (
          <span className="text-xs text-slate-400 font-mono flex-shrink-0">
            {agent.level}
          </span>
        )}

        {/* ON/OFF 토글 */}
        <button
          onClick={(e) => { e.stopPropagation(); onToggle(agent.agent_id, !agent.enabled); }}
          disabled={isUpdating || !canManage}
          className={`w-7 h-3.5 rounded-full relative flex-shrink-0 transition-colors disabled:opacity-40 ${
            agent.enabled ? "bg-ocean-600" : "bg-slate-700"
          }`}
        >
          <span
            className={`absolute top-0.5 w-2.5 h-2.5 rounded-full bg-white transition-all ${
              agent.enabled ? "left-3.5" : "left-0.5"
            }`}
          />
        </button>
      </div>

      {/* 이벤트 빈도 바 */}
      {count > 0 && (
        <div className="mx-2.5 mb-2 h-0.5 bg-slate-800 rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all"
            style={{ width: `${barPct}%`, background: color, opacity: 0.6 }}
          />
        </div>
      )}

      {/* 오류 표시 */}
      {(agent.failure_count ?? 0) > 0 && (
        <div className="px-2.5 pb-2 text-xs text-red-400">
          ⚠ 오류 {agent.failure_count}회
        </div>
      )}
    </div>
  );
}

// ── 파이프라인 컴포넌트 ──────────────────────────────────────────────────────

function HorizontalPipeline({
  steps,
  routes,
  criticalCount,
  warningCount,
  active,
  agentLevel,
}: {
  steps: PipelineStepDef[];
  routes?: { label: string; steps: PipelineStepDef[] }[];
  criticalCount: number;
  warningCount: number;
  active: boolean;
  agentLevel?: string;
}) {
  const [activeRoute, setActiveRoute] = useState(0);

  // routes가 있으면 탭 분기 뷰
  if (routes && routes.length > 0) {
    const current = routes[activeRoute];
    return (
      <div className="flex flex-col gap-4 w-full max-w-4xl mx-auto">
        {/* 경로 탭 */}
        <div className="flex gap-2 justify-center">
          {routes.map((r, i) => (
            <button
              key={i}
              onClick={() => setActiveRoute(i)}
              className={`text-xs px-3 py-1.5 rounded border font-semibold transition-colors ${
                activeRoute === i
                  ? "bg-blue-600/20 border-blue-500/60 text-blue-300"
                  : "border-slate-700 text-slate-500 hover:border-slate-500 hover:text-slate-300"
              }`}
            >
              {i === 0 ? "① " : "② "}{r.label}
            </button>
          ))}
        </div>
        <PipelineRow
          steps={current.steps}
          criticalCount={criticalCount}
          warningCount={warningCount}
          active={active}
          agentLevel={agentLevel}
        />
      </div>
    );
  }

  // 단일 경로
  return (
    <PipelineRow
      steps={steps}
      criticalCount={criticalCount}
      warningCount={warningCount}
      active={active}
      agentLevel={agentLevel}
    />
  );
}

/** 단계 목록을 가로로 렌더링하는 실제 행 */
function PipelineRow({
  steps,
  criticalCount,
  warningCount,
  active,
  agentLevel,
}: {
  steps: PipelineStepDef[];
  criticalCount: number;
  warningCount: number;
  active: boolean;
  agentLevel?: string;
}) {
  const hit = criticalCount > 0 || warningCount > 0;
  const nodes: React.ReactNode[] = [];

  steps.forEach((step, i) => {
    const isLast = i === steps.length - 1;

    // 레벨 조건 파싱: "L2+" → 현재 레벨이 L2 이상인지, "L3" → L3인지
    const levelReq = step.level;
    const levelNum = agentLevel ? parseInt(agentLevel.replace("L", "")) : 0;
    let levelSatisfied = true;
    if (levelReq) {
      if (levelReq.endsWith("+")) {
        const req = parseInt(levelReq.replace("L", "").replace("+", ""));
        levelSatisfied = levelNum >= req;
      } else {
        const req = parseInt(levelReq.replace("L", ""));
        levelSatisfied = levelNum >= req;
      }
    }

    const baseTone: "idle" | "active" | "alert" =
      step.tone ?? (isLast ? (hit ? "alert" : "active") : i === 0 ? "idle" : "active");
    const resolvedTone: "idle" | "active" | "alert" =
      (isLast || i === steps.length - 2) && hit ? "alert" : baseTone;

    nodes.push(
      <PipelineStep
        key={`step-${i}`}
        icon={step.icon}
        title={step.title}
        sub={step.sub}
        tone={levelSatisfied ? resolvedTone : "idle"}
        levelLabel={levelReq}
        levelSatisfied={levelSatisfied}
      />,
    );
    if (!isLast) {
      nodes.push(
        <PipelineRail key={`rail-${i}`} pulse={active && levelSatisfied} />,
      );
    }
  });

  return (
    <div className="flex items-center w-full max-w-4xl mx-auto justify-between relative px-2 py-6">
      {nodes}
    </div>
  );
}

function PipelineRail({ pulse }: { pulse: boolean }) {
  return (
    <div
      className="flex-1 h-[2px] mx-3 relative"
      style={{
        backgroundImage: pulse
          ? "linear-gradient(90deg, #3b82f6 50%, transparent 50%)"
          : "linear-gradient(90deg, #334155 50%, transparent 50%)",
        backgroundSize: "8px 1px",
      }}
    >
      {pulse && (
        <div className="absolute -top-1 w-2 h-2 bg-blue-500 rounded-full animate-ping left-[30%]" />
      )}
    </div>
  );
}

function PipelineStep({
  icon, title, sub, tone, levelLabel, levelSatisfied,
}: {
  icon: string;
  title: string;
  sub: string;
  tone: "idle" | "active" | "alert";
  levelLabel?: string;
  levelSatisfied?: boolean;
}) {
  const toneClass =
    tone === "alert"
      ? "bg-red-500/20 border-red-500 text-red-400"
      : tone === "active"
        ? "bg-blue-600/10 border-blue-500 text-blue-400"
        : "bg-slate-900 border-slate-700 text-slate-300";

  const dimmed = levelLabel && !levelSatisfied;

  return (
    <div className={`z-10 flex flex-col items-center gap-2 ${dimmed ? "opacity-35" : ""}`}>
      <div
        className={`w-16 h-16 rounded-xl border-2 flex items-center justify-center shadow-2xl ${toneClass} ${tone === "alert" ? "animate-pulse" : ""}`}
      >
        <span className="text-3xl">{icon}</span>
      </div>
      <div className="text-center">
        <div className="text-sm font-bold text-white whitespace-pre-line leading-tight">{title}</div>
        <div className="text-xs text-slate-500 whitespace-pre-line leading-tight mt-0.5">{sub}</div>
        {/* 레벨 조건 뱃지 */}
        {levelLabel && (
          <span className={`inline-block mt-1 text-xs px-1.5 py-0.5 rounded border font-mono ${
            levelSatisfied
              ? "text-green-400 border-green-700/50 bg-green-950/30"
              : "text-slate-600 border-slate-700 bg-slate-900"
          }`}>
            {levelLabel}
          </span>
        )}
      </div>
    </div>
  );
}

// ── 이벤트 로그 카드 ──────────────────────────────────────────────────────────

function LogCard({
  log, expanded, onToggle, getPlatformName,
}: {
  log: ActivityLogEntry;
  expanded: boolean;
  onToggle: () => void;
  getPlatformName: (id: string) => string;
}) {
  const meta = AGENT_META[log.agent_id];
  const color = meta?.color ?? "#7ab8d9";
  const isAI = isAIAgent(log.agent_id);
  const isFallback = log.model?.includes("fallback");
  const sev = SEV[log.severity as keyof typeof SEV] ?? SEV.info;
  const isCPA = log.alert_type === "cpa";

  const cpa_nm = typeof log.metadata?.cpa_nm === "number" ? log.metadata.cpa_nm : null;
  const tcpa_min = typeof log.metadata?.tcpa_min === "number" ? log.metadata.tcpa_min : null;

  return (
    <div className={`rounded-lg border-l-2 border border-slate-800/50 overflow-hidden ${sev.border}`}>
      {/* 요약 행 */}
      <div
        className={`px-3 py-2.5 cursor-pointer transition-colors hover:bg-slate-800/20 ${sev.headerBg}`}
        onClick={onToggle}
      >
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-bold flex-shrink-0" style={{ color }}>
            {meta?.name ?? log.agent_id}
          </span>
          <span
            className={`text-xs px-1.5 py-0.5 rounded flex-shrink-0 border ${
              isAI
                ? "bg-violet-900/40 text-violet-300 border-violet-800/50"
                : "bg-slate-800/60 text-slate-400 border-slate-700/40"
            }`}
          >
            {isAI ? "AI" : "Rule"}
          </span>
          <span className="text-xs px-1.5 py-0.5 rounded bg-slate-800/60 text-slate-300 border border-slate-700/40 flex-shrink-0">
            {ALERT_TYPE_KR[log.alert_type] ?? log.alert_type}
          </span>
          <span className={`text-xs font-bold flex-shrink-0 px-1.5 py-0.5 rounded ${sev.badge}`}>
            {sev.label}
          </span>
          {isFallback && (
            <span className="text-xs text-amber-400/60 flex-shrink-0">fallback</span>
          )}
          <span className="ml-auto text-xs text-slate-500 flex-shrink-0">
            {formatDistanceToNow(new Date(log.timestamp), { addSuffix: true, locale: ko })}
          </span>
          <span className={`text-slate-400 text-xs transition-transform flex-shrink-0 ${expanded ? "rotate-90" : ""}`}>
            ▶
          </span>
        </div>

        {isCPA && log.platform_ids.length === 2 ? (
          <div className="mt-2 flex items-center gap-2">
            <span className="text-xs px-2 py-1 rounded bg-slate-800 text-slate-200 font-mono border border-slate-700/40">
              {getPlatformName(log.platform_ids[0])}
            </span>
            <div className="flex-1 flex flex-col items-center">
              <div className={`w-full h-px ${sev.dot === "bg-red-500" ? "bg-red-500/40" : "bg-amber-500/40"}`} />
              <div className="flex gap-3 text-xs mt-0.5">
                {cpa_nm !== null && (
                  <span className={sev.text + " font-mono font-bold"}>{cpa_nm.toFixed(2)} NM</span>
                )}
                {tcpa_min !== null && (
                  <span className="text-slate-400 font-mono">TCPA {tcpa_min.toFixed(1)}분</span>
                )}
              </div>
            </div>
            <span className="text-xs px-2 py-1 rounded bg-slate-800 text-slate-200 font-mono border border-slate-700/40">
              {getPlatformName(log.platform_ids[1])}
            </span>
          </div>
        ) : (
          <>
            <p className="mt-1.5 text-sm text-slate-300 leading-snug line-clamp-1">{log.message}</p>
            {log.platform_ids.length > 0 && (
              <div className="flex gap-1 mt-1.5 flex-wrap">
                {log.platform_ids.slice(0, 4).map((id) => (
                  <span key={id} className="text-xs px-1.5 py-0.5 bg-slate-800 text-slate-300 rounded font-mono border border-slate-700/30">
                    {getPlatformName(id)}
                  </span>
                ))}
                {log.platform_ids.length > 4 && (
                  <span className="text-xs text-slate-400">+{log.platform_ids.length - 4}</span>
                )}
              </div>
            )}
          </>
        )}
      </div>

      {/* 상세 패널 */}
      {expanded && (
        <div className="border-t border-slate-800/40 bg-slate-900/40">
          <div className="px-4 pt-3 pb-1 flex items-center gap-3 text-xs text-slate-400">
            <span>{format(new Date(log.timestamp), "yyyy/MM/dd HH:mm:ss")}</span>
            {log.model && (
              <span className="px-1.5 py-0.5 bg-slate-800/60 text-slate-400 rounded border border-slate-700/40">
                {log.model}
              </span>
            )}
          </div>

          <DetailSection title="발생 원인 / 입력 데이터" icon="→">
            {meta && (
              <div className="space-y-1.5">
                <DataRow label="트리거 조건" value={meta.trigger} />
                <DataRow label="분석 대상" value={meta.input} />
                {isAI && meta.triggeredBy && AGENT_META[meta.triggeredBy] && (
                  <DataRow
                    label="트리거 에이전트"
                    value={AGENT_META[meta.triggeredBy].name}
                    highlight={AGENT_META[meta.triggeredBy].color}
                  />
                )}
                {isCPA && (cpa_nm !== null || tcpa_min !== null) && (
                  <div className="flex gap-4 mt-1">
                    {cpa_nm !== null && <MetricBadge label="CPA" value={`${cpa_nm.toFixed(3)} NM`} sev={log.severity} />}
                    {tcpa_min !== null && <MetricBadge label="TCPA" value={`${tcpa_min.toFixed(1)} 분`} sev={log.severity} />}
                  </div>
                )}
                {Object.entries(log.metadata ?? {})
                  .filter(([k]) => !["cpa_nm", "tcpa_min", "dedup_key", "ai_model"].includes(k))
                  .map(([k, v]) => <DataRow key={k} label={k} value={String(v)} />)}
              </div>
            )}
            {log.platform_ids.length > 0 && (
              <div className="mt-2 flex gap-2 flex-wrap">
                {log.platform_ids.map((id, i) => (
                  <span key={id} className="text-xs px-2 py-1 bg-slate-800/60 text-slate-200 rounded font-mono border border-slate-700/40">
                    {isCPA && log.platform_ids.length === 2 ? (
                      <>
                        <span className="text-slate-500 mr-1">{i === 0 ? "선박 A" : "선박 B"}</span>
                        {id.replace(/^MMSI-/, "")}
                      </>
                    ) : id.replace(/^MMSI-/, "")}
                  </span>
                ))}
              </div>
            )}
          </DetailSection>

          <DetailSection title="처리 결과 / 출력" icon="⬡">
            <p className="text-xs text-slate-200 leading-relaxed">{log.message}</p>
            {meta && <div className="mt-1.5 text-xs text-slate-500">{meta.output}</div>}
          </DetailSection>

          {isAI && (
            <DetailSection
              title={isFallback ? "AI 권고 (fallback 모드)" : "AI 권고"}
              icon="✦"
              accent={isFallback ? "amber" : "cyan"}
            >
              {log.recommendation ? (
                <pre className="text-xs text-slate-100 leading-relaxed whitespace-pre-wrap font-sans">
                  {log.recommendation}
                </pre>
              ) : (
                <p className="text-xs text-slate-400 italic">
                  {log.model?.includes("L1") || !log.model
                    ? "L1 모드 — 권고 생성 비활성"
                    : "LLM 호출 결과 없음"}
                </p>
              )}
            </DetailSection>
          )}
        </div>
      )}
    </div>
  );
}

// ── 공통 UI 부품 ──────────────────────────────────────────────────────────────

function Stat({
  label, value, color, pulse,
}: {
  label: string;
  value: string | number;
  color?: string;
  pulse?: boolean;
}) {
  return (
    <div className="flex items-center gap-1.5">
      {pulse && <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />}
      <span className="text-slate-500">{label}</span>
      <span className={`font-mono font-bold ${color ?? "text-white"}`}>{value}</span>
    </div>
  );
}

function InfoCell({
  label, value, color,
}: {
  label: string;
  value: string;
  color?: string;
}) {
  return (
    <div className="bg-slate-900/50 border border-slate-800 p-2 rounded">
      <div className="text-xs text-slate-500 uppercase font-bold mb-0.5">{label}</div>
      <div className={`text-sm font-mono font-bold ${color ?? "text-slate-300"}`}>{value}</div>
    </div>
  );
}

function FlowRow({
  icon, label, value, color,
}: {
  icon: string;
  label: string;
  value: string;
  color: string;
}) {
  return (
    <div className="flex items-start gap-1.5 text-sm">
      <span className={`${color} flex-shrink-0 mt-0.5`}>{icon}</span>
      <div>
        <span className="text-slate-500">{label}: </span>
        <span className="text-slate-300 leading-snug">{value}</span>
      </div>
    </div>
  );
}

function DetailSection({
  title, icon, accent = "ocean", children,
}: {
  title: string;
  icon: string;
  accent?: "ocean" | "cyan" | "amber";
  children: React.ReactNode;
}) {
  const accentColor = { ocean: "text-slate-400", cyan: "text-cyan-400", amber: "text-amber-400" }[accent];
  return (
    <div className="px-4 py-2.5 border-t border-slate-800/30">
      <div className={`flex items-center gap-1.5 text-sm font-semibold mb-2 ${accentColor}`}>
        <span>{icon}</span>
        <span>{title}</span>
      </div>
      {children}
    </div>
  );
}

function DataRow({ label, value, highlight }: { label: string; value: string; highlight?: string }) {
  return (
    <div className="flex items-start gap-2 text-sm">
      <span className="text-slate-500 flex-shrink-0 w-24">{label}</span>
      <span className="text-slate-300 leading-snug" style={highlight ? { color: highlight } : undefined}>
        {value}
      </span>
    </div>
  );
}

function MetricBadge({ label, value, sev }: { label: string; value: string; sev: string }) {
  const color =
    sev === "critical"
      ? "text-red-300 border-red-700/50 bg-red-950/50"
      : sev === "warning"
        ? "text-amber-300 border-amber-700/50 bg-amber-950/50"
        : "text-blue-300 border-blue-700/50 bg-blue-950/50";
  return (
    <div className={`rounded px-2.5 py-1.5 border ${color} text-center`}>
      <div className="text-xs opacity-60">{label}</div>
      <div className="text-base font-mono font-bold">{value}</div>
    </div>
  );
}
