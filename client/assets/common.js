(function () {
  function normalizeBaseUrl(value, fallback) {
    const raw = String(value || "").trim();
    if (!raw) return fallback;
    return raw.endsWith("/") ? raw.slice(0, -1) : raw;
  }

  function defaultHttpBase(port) {
    const hostname = window.location.hostname || "127.0.0.1";
    const protocol = window.location.protocol === "file:" ? "http:" : window.location.protocol || "http:";
    return `${protocol}//${hostname}:${port}`;
  }

  const storedConfig = (() => {
    try {
      return JSON.parse(localStorage.getItem("cowater.client.config") || "{}");
    } catch {
      return {};
    }
  })();

  const runtimeConfig = window.__COWATER_CONFIG__ || {};
  const config = {
    registryBase: normalizeBaseUrl(
      runtimeConfig.registryBase || storedConfig.registryBase || window.localStorage.getItem("cowater.registryBase"),
      defaultHttpBase(8280),
    ),
    systemBase: normalizeBaseUrl(
      runtimeConfig.systemBase || storedConfig.systemBase || window.localStorage.getItem("cowater.systemBase"),
      defaultHttpBase(9116),
    ),
    mothWsBase: normalizeBaseUrl(
      runtimeConfig.mothWsBase || storedConfig.mothWsBase || window.localStorage.getItem("cowater.mothWsBase"),
      "wss://cobot.center:8287",
    ),
  };

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function formatTimestamp(value) {
    if (!value) return "-";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString();
  }

  function qs(name) {
    return new URLSearchParams(window.location.search).get(name);
  }

  function setText(id, value) {
    const node = document.getElementById(id);
    if (node) node.textContent = value;
  }

  function setHtml(id, value) {
    const node = document.getElementById(id);
    if (node) node.innerHTML = value;
  }

  function apiUrl(base, path) {
    return new URL(path, base).toString();
  }

  async function requestJson(base, path, options = {}) {
    const response = await fetch(apiUrl(base, path), {
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
      ...options,
    });
    const contentType = response.headers.get("content-type") || "";
    const isJson = contentType.includes("application/json");
    const body = isJson ? await response.json() : await response.text();
    if (!response.ok) {
      const detail =
        body && typeof body === "object" && "detail" in body ? body.detail : body;
      throw new Error(
        typeof detail === "string" ? detail : `HTTP ${response.status}`,
      );
    }
    return body;
  }

  window.CoWaterUI = {
    config,
    escapeHtml,
    formatTimestamp,
    qs,
    setText,
    setHtml,
    apiUrl,
    requestJson,
    normalizeBaseUrl,
  };
})();
