(function () {
  try {
    function normalizeBaseUrl(value, fallback) {
      const raw = String(value || "").trim();
      if (!raw) return fallback;
      return raw.endsWith("/") ? raw.slice(0, -1) : raw;
    }

    function defaultHttpBase(port) {
      const hostname = window.location.hostname || "127.0.0.1";
      const protocol =
        window.location.protocol === "file:"
          ? "http:"
          : window.location.protocol || "http:";
      return `${protocol}//${hostname}:${port}`;
    }

    const storedConfig = (() => {
      try {
        return JSON.parse(
          localStorage.getItem("cowater.client.config") || "{}",
        );
      } catch {
        return {};
      }
    })();

    const runtimeConfig = window.__COWATER_CONFIG__ || {};
    const config = {
      registryBase: normalizeBaseUrl(
        runtimeConfig.registryBase ||
          storedConfig.registryBase ||
          (typeof localStorage !== "undefined"
            ? window.localStorage.getItem("cowater.registryBase")
            : null),
        defaultHttpBase(8280),
      ),
      systemBase: normalizeBaseUrl(
        runtimeConfig.systemBase ||
          storedConfig.systemBase ||
          (typeof localStorage !== "undefined"
            ? window.localStorage.getItem("cowater.systemBase")
            : null),
        defaultHttpBase(9116),
      ),
      mothWsBase: normalizeBaseUrl(
        runtimeConfig.mothWsBase ||
          storedConfig.mothWsBase ||
          (typeof localStorage !== "undefined"
            ? window.localStorage.getItem("cowater.mothWsBase")
            : null),
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

    function getOrCreateCsrfToken() {
      try {
        let token = sessionStorage.getItem("cowater_csrf_token");
        if (!token) {
          const arr = new Uint8Array(32);
          crypto.getRandomValues(arr);
          token = Array.from(arr, (byte) =>
            byte.toString(16).padStart(2, "0"),
          ).join("");
          sessionStorage.setItem("cowater_csrf_token", token);
        }
        return token;
      } catch {
        return ""; // fallback: no CSRF token
      }
    }

    async function requestJson(base, path, options = {}) {
      const csrfToken = getOrCreateCsrfToken();
      const headers = {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken,
        ...(options.headers || {}),
      };
      const response = await fetch(apiUrl(base, path), {
        ...options,
        headers,
      });
      const contentType = response.headers.get("content-type") || "";
      const isJson = contentType.includes("application/json");
      const body = isJson ? await response.json() : await response.text();
      if (!response.ok) {
        const detail =
          body && typeof body === "object" && "detail" in body
            ? body.detail
            : body;
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
  } catch (e) {
    console.error("[CoWaterUI] Initialization error:", e);
    window.CoWaterUI = {
      config: {
        registryBase: "http://127.0.0.1:8280",
        systemBase: "http://127.0.0.1:9116",
        mothWsBase: "wss://cobot.center:8287",
      },
      escapeHtml: (v) => String(v),
      formatTimestamp: (v) => String(v),
      qs: () => null,
      setText: () => {},
      setHtml: () => {},
      apiUrl: (b, p) => new URL(p, b).toString(),
      requestJson: async () => ({}),
      normalizeBaseUrl: (v, f) => v || f,
    };
  }
})();
