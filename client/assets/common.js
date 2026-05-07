(function () {
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
    escapeHtml,
    formatTimestamp,
    qs,
    setText,
    setHtml,
    apiUrl,
    requestJson,
  };
})();
