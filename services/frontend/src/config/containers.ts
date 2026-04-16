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
  hasAgentsEndpoint?: boolean;
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
    hasAgentsEndpoint: true,
  },
  {
    id: "analysis",
    name: "Analysis",
    port: 7705,
    url: getAnalysisAgentsApiUrl(),
    color: "#a78bfa",
    icon: "🧠",
    agents: ["Anomaly AI"],
    hasAgentsEndpoint: false,
  },
  {
    id: "response",
    name: "Response",
    port: 7706,
    url: getResponseAgentsApiUrl(),
    color: "#f87171",
    icon: "⚡",
    agents: ["Alert Creator", "Distress Agent"],
    hasAgentsEndpoint: false,
  },
  {
    id: "report",
    name: "Report",
    port: 7709,
    url: getReportAgentsApiUrl(),
    color: "#34d399",
    icon: "📋",
    agents: ["Report Agent"],
    hasAgentsEndpoint: false,
  },
  {
    id: "control",
    name: "Control",
    port: 7701,
    url: getControlAgentsApiUrl(),
    color: "#38bdf8",
    icon: "💬",
    agents: ["Chat Agent"],
    hasAgentsEndpoint: true,
  },
  {
    id: "learning",
    name: "Learning",
    port: 7708,
    url: getLearningAgentsApiUrl(),
    color: "#fbbf24",
    icon: "📚",
    agents: ["Learning Agent"],
    hasAgentsEndpoint: false,
  },
  {
    id: "supervision",
    name: "Supervision",
    port: 7707,
    url: getSupervisionAgentsApiUrl(),
    color: "#8b5cf6",
    icon: "👁",
    agents: ["Supervisor"],
    hasAgentsEndpoint: true,
  },
];
