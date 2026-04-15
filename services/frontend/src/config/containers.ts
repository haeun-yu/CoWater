import {
  getDetectionAgentsApiUrl,
  getAnalysisAgentsApiUrl,
  getResponseAgentsApiUrl,
  getReportAgentsApiUrl,
  getLearningAgentsApiUrl,
  getSupervisionAgentsApiUrl,
  getControlAgentsApiUrl,
} from "@/lib/publicUrl";

export interface ContainerDef {
  id: string;
  name: string;
  port: number;
  url: string;
  icon: string;
  color?: string;
  agents: string[];
}

export const CONTAINERS: ContainerDef[] = [
  {
    id: "detection",
    name: "Detection",
    port: 7704,
    url: getDetectionAgentsApiUrl(),
    color: "#2e8dd4",
    icon: "🔍",
    agents: ["CPA", "Anomaly", "Zone", "Distress"],
  },
  {
    id: "analysis",
    name: "Analysis",
    port: 7705,
    url: getAnalysisAgentsApiUrl(),
    color: "#a78bfa",
    icon: "🧠",
    agents: ["Anomaly AI", "Distress AI"],
  },
  {
    id: "response",
    name: "Response",
    port: 7706,
    url: getResponseAgentsApiUrl(),
    color: "#f87171",
    icon: "⚡",
    agents: ["Alert Creator"],
  },
  {
    id: "report",
    name: "Report",
    port: 7709,
    url: getReportAgentsApiUrl(),
    color: "#34d399",
    icon: "📋",
    agents: ["AI Report Agent"],
  },
  {
    id: "control",
    name: "Control",
    port: 7701,
    url: getControlAgentsApiUrl(),
    color: "#38bdf8",
    icon: "💬",
    agents: ["Chat Agent"],
  },
  {
    id: "learning",
    name: "Learning",
    port: 7708,
    url: getLearningAgentsApiUrl(),
    color: "#fbbf24",
    icon: "📚",
    agents: ["Learning Agent"],
  },
  {
    id: "supervision",
    name: "Supervision",
    port: 7707,
    url: getSupervisionAgentsApiUrl(),
    color: "#8b5cf6",
    icon: "👁",
    agents: ["Supervisor"],
  },
];
