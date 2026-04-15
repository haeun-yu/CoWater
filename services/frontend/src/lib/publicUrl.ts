const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "0.0.0.0"]);

function browserHostname() {
  if (typeof window === "undefined") return "localhost";
  return window.location.hostname || "localhost";
}

function browserProtocol(kind: "http" | "ws") {
  if (typeof window === "undefined") return kind;
  const secure = window.location.protocol === "https:";
  if (kind === "ws") return secure ? "wss" : "ws";
  return secure ? "https" : "http";
}

function defaultUrl(kind: "http" | "ws", port: number) {
  return `${browserProtocol(kind)}://${browserHostname()}:${port}`;
}

function normalizePublicUrl(value: string | undefined, kind: "http" | "ws", port: number) {
  const raw = value || defaultUrl(kind, port);
  if (typeof window === "undefined") return raw;

  try {
    const url = new URL(raw);
    const host = browserHostname();
    if (LOCAL_HOSTS.has(url.hostname) && !LOCAL_HOSTS.has(host)) {
      url.hostname = host;
    }
    return url.toString().replace(/\/$/, "");
  } catch {
    return raw;
  }
}

export function getCoreApiUrl() {
  return normalizePublicUrl(process.env.NEXT_PUBLIC_API_URL, "http", 7700);
}

export function getCoreWsUrl() {
  return normalizePublicUrl(process.env.NEXT_PUBLIC_WS_URL, "ws", 7700);
}

export function getPositionWsUrl() {
  return normalizePublicUrl(process.env.NEXT_PUBLIC_POSITION_WS_URL, "ws", 7703);
}

// Agent service URL factory
const AGENT_SERVICES = {
  detection: { env: "NEXT_PUBLIC_DETECTION_AGENTS_URL", port: 7704 },
  analysis: { env: "NEXT_PUBLIC_ANALYSIS_AGENTS_URL", port: 7705 },
  response: { env: "NEXT_PUBLIC_RESPONSE_AGENTS_URL", port: 7706 },
  report: { env: "NEXT_PUBLIC_REPORT_AGENTS_URL", port: 7709 },
  learning: { env: "NEXT_PUBLIC_LEARNING_AGENTS_URL", port: 7708 },
  supervision: { env: "NEXT_PUBLIC_SUPERVISION_AGENTS_URL", port: 7707 },
  control: { env: "NEXT_PUBLIC_CONTROL_AGENTS_URL", port: 7701 },
} as const;

function getAgentApiUrl(service: keyof typeof AGENT_SERVICES) {
  const config = AGENT_SERVICES[service];
  return normalizePublicUrl(process.env[config.env], "http", config.port);
}

// Exported functions for backwards compatibility
export function getDetectionAgentsApiUrl() {
  return getAgentApiUrl("detection");
}

export function getAnalysisAgentsApiUrl() {
  return getAgentApiUrl("analysis");
}

export function getResponseAgentsApiUrl() {
  return getAgentApiUrl("response");
}

export function getReportAgentsApiUrl() {
  return getAgentApiUrl("report");
}

export function getLearningAgentsApiUrl() {
  return getAgentApiUrl("learning");
}

export function getSupervisionAgentsApiUrl() {
  return getAgentApiUrl("supervision");
}

export function getControlAgentsApiUrl() {
  return getAgentApiUrl("control");
}
