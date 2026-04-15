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

export function getAgentsApiUrl() {
  return normalizePublicUrl(process.env.NEXT_PUBLIC_AGENTS_URL, "http", 7701);
}

export function getDetectionAgentsApiUrl() {
  return normalizePublicUrl(process.env.NEXT_PUBLIC_DETECTION_AGENTS_URL, "http", 7704);
}

export function getAnalysisAgentsApiUrl() {
  return normalizePublicUrl(process.env.NEXT_PUBLIC_ANALYSIS_AGENTS_URL, "http", 7705);
}

export function getResponseAgentsApiUrl() {
  return normalizePublicUrl(process.env.NEXT_PUBLIC_RESPONSE_AGENTS_URL, "http", 7706);
}

export function getReportAgentsApiUrl() {
  return normalizePublicUrl(process.env.NEXT_PUBLIC_REPORT_AGENTS_URL, "http", 7709);
}

export function getLearningAgentsApiUrl() {
  return normalizePublicUrl(process.env.NEXT_PUBLIC_LEARNING_AGENTS_URL, "http", 7708);
}

export function getSupervisionAgentsApiUrl() {
  return normalizePublicUrl(process.env.NEXT_PUBLIC_SUPERVISION_AGENTS_URL, "http", 7707);
}

export function getControlAgentsApiUrl() {
  return normalizePublicUrl(process.env.NEXT_PUBLIC_CONTROL_AGENTS_URL, "http", 7701);
}
