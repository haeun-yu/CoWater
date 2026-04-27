const STORAGE_KEY = "cowater.systemCenter.apiBase";
const DEFAULT_API_BASE = "http://127.0.0.1:9012";

const $ = (id) => document.getElementById(id);

const apiBase = () => ($("api-base")?.value || localStorage.getItem(STORAGE_KEY) || DEFAULT_API_BASE).trim();
const api = (path) => new URL(path, apiBase()).toString();

const saveApiBase = (value) => localStorage.setItem(STORAGE_KEY, value.trim());

const j = async (path, opts = {}) => {
  const res = await fetch(api(path), {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
  return body;
};

const pretty = (value) => JSON.stringify(value, null, 2);

const clip = (value, n = 140) => {
  const s = typeof value === "string" ? value : pretty(value);
  return s.length > n ? `${s.slice(0, n)}...` : s;
};

const badge = (text, tone = "info") => `<span class="badge ${tone}">${text}</span>`;

const esc = (value) =>
  String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");

function setText(id, value) {
  const node = $(id);
  if (node) node.textContent = value;
}

function setHtml(id, value) {
  const node = $(id);
  if (node) node.innerHTML = value;
}

function menuActive() {
  const page = document.body.dataset.page || "";
  document.querySelectorAll("[data-nav-link]").forEach((node) => {
    node.classList.toggle("active", node.dataset.navLink === page);
  });
}

function renderItems(items, id, kind) {
  const el = $(id);
  if (!el) return;
  if (!items || !items.length) {
    el.innerHTML = '<div class="muted">empty</div>';
    return;
  }

  el.innerHTML = items
    .map((item) => {
      const title =
        item.title || item.message || item.summary || item.event_type || item.alert_type || item.action || item.kind || "item";
      const meta = item.role || item.source_role || item.from_agent_id || item.event_type || item.alert_type || "";
      const sub = item.to_agent_id || item.target_agent_id || item.source_id || item.mission_id || item.task_id || "";
      const buttons =
        kind === "alert" && ["waiting", "planned", "notified"].includes(item.status)
          ? `<div class="item-actions"><button class="ghost" data-ack="${esc(item.alert_id)}">Ack</button></div>`
          : "";
      const severityTone =
        item.severity === "critical" ? "danger" : item.severity === "warning" ? "warn" : item.severity ? "info" : "info";
      const stateTone =
        item.status === "done" || item.state === "completed" || item.status === "approved" ? "ok" : "info";

      return `
        <div class="item">
          <div class="item-head">
            <div>
              <strong>${esc(title)}</strong>
              <div class="muted tiny">${esc(meta)}${item.transport ? ` · ${esc(item.transport)}` : ""}${sub ? ` → ${esc(sub)}` : ""}</div>
            </div>
            <div>${item.severity ? badge(item.severity, severityTone) : ""}</div>
          </div>
          <div style="margin-top:8px;">
            ${badge(item.status || item.state || "new", stateTone)}
            ${item.decision_strategy ? badge(item.decision_strategy, item.decision_strategy === "hybrid" ? "warn" : "info") : ""}
          </div>
          <div class="muted tiny" style="margin-top:8px;">${esc(clip(item.summary || item.message || item.recommended_action || "", 180))}</div>
          <pre>${esc(pretty(item))}</pre>
          ${buttons}
        </div>
      `;
    })
    .join("");
}

async function refresh() {
  const [meta, state] = await Promise.all([j("/meta"), j("/state")]);

  if ($("status")) {
    $("status").textContent = state.connected ? "connected" : "disconnected";
  }

  if ($("agent-meta")) {
    $("agent-meta").innerHTML = [
      badge(meta.agent.role, "info"),
      badge(meta.agent.id, "info"),
      badge(meta.agent.mission_prefix, "warn"),
    ].join(" ");
  }

  if ($("analysis-meta")) {
    const llmEnabled = meta.analysis?.llm_enabled ? "enabled" : "disabled";
    $("analysis-meta").innerHTML = [
      badge(`LLM ${llmEnabled}`, meta.analysis?.llm_enabled ? "warn" : "info"),
      badge(`auto response ${meta.analysis?.auto_response ? "on" : "off"}`, meta.analysis?.auto_response ? "ok" : "warn"),
    ].join(" ");
  }

  if ($("registry-meta")) {
    $("registry-meta").innerHTML = [
      badge(state.registry_snapshot?.device_registry_url || meta.registry?.device_registry_url || "-", "info"),
      badge(`children ${state.children?.length || 0}`, "info"),
      badge(`events ${state.events?.length || 0}`, "info"),
      badge(`alerts ${state.alerts?.length || 0}`, "warn"),
      badge(`responses ${state.responses?.length || 0}`, "warn"),
    ].join(" ");
  }

  if ($("state")) $("state").textContent = pretty(state);
  if ($("meta")) $("meta").textContent = pretty(meta);

  renderItems(state.children || [], "children", "child");
  renderItems(state.missions || [], "missions", "mission");
  renderItems(state.events || [], "events", "event");
  renderItems(state.alerts || [], "alerts", "alert");
  renderItems(state.responses || [], "responses", "response");
  renderItems(state.inbox || [], "inbox", "inbox");
  renderItems(state.outbox || [], "outbox", "outbox");
}

function bindConfig() {
  const input = $("api-base");
  if (!input) return;
  input.value = localStorage.getItem(STORAGE_KEY) || DEFAULT_API_BASE;
  input.addEventListener("change", () => saveApiBase(input.value));
}

function bindCommonActions() {
  const refreshBtn = $("refresh");
  if (refreshBtn) refreshBtn.onclick = () => refresh().catch((e) => $("status") && ($("status").textContent = e.message));

  const syncBtn = $("sync");
  if (syncBtn) {
    syncBtn.onclick = async () => {
      await j("/registry/sync", { method: "POST" });
      await refresh();
    };
  }

  const resetBtn = $("reset");
  if (resetBtn) {
    resetBtn.onclick = async () => {
      await j("/reset", { method: "POST" });
      await refresh();
    };
  }

  const ingestBtn = $("ingest-event");
  if (ingestBtn) {
    ingestBtn.onclick = async () => {
      let payload = {};
      try {
        payload = JSON.parse(($("event-payload")?.value || "{}").trim() || "{}");
      } catch (_error) {
        alert("payload JSON error");
        return;
      }
      await j("/events/ingest", {
        method: "POST",
        body: JSON.stringify({
          event_type: $("event-type")?.value.trim() || "event.report",
          source_id: $("event-source-id")?.value.trim() || "unknown",
          source_role: $("event-source-role")?.value.trim() || "unknown",
          severity: $("event-severity")?.value || "info",
          summary: $("event-summary")?.value.trim() || null,
          target_role: $("event-target-role")?.value.trim() || null,
          target_agent_id: $("event-target-agent")?.value.trim() || null,
          auto_response: $("event-auto-response")?.value === "true",
          requires_user_approval: $("event-requires-approval")?.value === "true",
          payload,
        }),
      });
      await refresh();
    };
  }

  document.addEventListener("click", async (event) => {
    const ackId = event.target?.dataset?.ack;
    if (!ackId) return;
    await j(`/alerts/${ackId}/ack`, {
      method: "POST",
      body: JSON.stringify({ approved: true, notes: "acked from dashboard" }),
    });
    await refresh();
  });
}

function bindPageButtons() {
  const page = document.body.dataset.page || "";
  if (page === "dashboard") {
    const showRaw = $("raw-state-toggle");
    if (showRaw) {
      showRaw.onclick = async () => refresh();
    }
  }
}

function init() {
  menuActive();
  bindConfig();
  bindCommonActions();
  bindPageButtons();
  refresh().catch((e) => {
    const status = $("status");
    if (status) status.textContent = e.message;
  });
}

document.addEventListener("DOMContentLoaded", init);
