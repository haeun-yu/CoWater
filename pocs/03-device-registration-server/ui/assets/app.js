const STORAGE_KEYS = {
  apiBase: "cowater.deviceRegistration.apiBase",
  secretKey: "cowater.deviceRegistration.secretKey",
};

const DEFAULT_API_BASE = "http://127.0.0.1:8003";

function getApiBase() {
  return localStorage.getItem(STORAGE_KEYS.apiBase) || DEFAULT_API_BASE;
}

function setApiBase(value) {
  localStorage.setItem(STORAGE_KEYS.apiBase, value.trim());
}

function getSecretKey() {
  return localStorage.getItem(STORAGE_KEYS.secretKey) || "server-secret";
}

function setSecretKey(value) {
  localStorage.setItem(STORAGE_KEYS.secretKey, value.trim());
}

function qs(name) {
  return new URLSearchParams(window.location.search).get(name);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function prettyJson(value) {
  return JSON.stringify(value, null, 2);
}

function formatTimestamp(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function apiUrl(path) {
  return new URL(path, getApiBase()).toString();
}

async function requestJson(path, options = {}) {
  const response = await fetch(apiUrl(path), {
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
    const detail = body && typeof body === "object" && "detail" in body ? body.detail : body;
    throw new Error(typeof detail === "string" ? detail : `HTTP ${response.status}`);
  }
  return body;
}

function setText(id, value) {
  const node = document.getElementById(id);
  if (node) node.textContent = value;
}

function setHtml(id, value) {
  const node = document.getElementById(id);
  if (node) node.innerHTML = value;
}

function activeNav() {
  const page = document.body.dataset.page || "";
  document.querySelectorAll("[data-nav-link]").forEach((node) => {
    node.classList.toggle("active", node.dataset.navLink === page);
  });
}

function bindConfigInputs() {
  document.querySelectorAll("[data-bind='apiBase']").forEach((input) => {
    input.value = getApiBase();
    input.addEventListener("change", () => setApiBase(input.value));
  });
  document.querySelectorAll("[data-bind='secretKey']").forEach((input) => {
    input.value = getSecretKey();
    input.addEventListener("change", () => setSecretKey(input.value));
  });
}

function statusBadge(connected) {
  return connected
    ? '<span class="badge ok">connected</span>'
    : '<span class="badge warn">disconnected</span>';
}

function renderEndpointList(device) {
  return device.tracks
    .map(
      (track) => `
        <div class="device-card">
          <div class="device-head">
            <div>
              <h3 class="device-title">${escapeHtml(track.name)}</h3>
              <div class="device-meta">
                <span class="badge">${escapeHtml(track.type)}</span>
                <span class="badge">${escapeHtml(track.endpoint)}</span>
              </div>
            </div>
          </div>
        </div>
      `,
    )
    .join("");
}

async function loadMeta() {
  return requestJson("/meta");
}

async function loadDevices() {
  return requestJson("/devices");
}

function countTracks(devices, kind) {
  return devices.reduce(
    (total, device) =>
      total +
      device.tracks.filter((track) => !kind || track.type === kind).length,
    0,
  );
}

function coreActionsCount(devices) {
  const seen = new Set();
  devices.forEach((device) => {
    (device.actions?.core || []).forEach((action) => seen.add(action));
  });
  return seen.size;
}

function renderDashboardDevices(devices) {
  const host = document.getElementById("recent-devices");
  if (!host) return;
  if (!devices.length) {
    host.innerHTML = `<div class="panel"><p class="lead">No devices registered yet. Start from the registration page.</p></div>`;
    return;
  }
  host.innerHTML = devices
    .slice(0, 6)
    .map(
      (device) => `
        <div class="device-card">
          <div class="device-head">
            <div>
              <h3 class="device-title">${escapeHtml(device.name)}</h3>
              <div class="device-meta">
                ${statusBadge(device.connected)}
                <span class="badge">id ${device.id}</span>
                <span class="badge">${escapeHtml(device.main_video_track_name || "-")}</span>
              </div>
            </div>
            <a class="button" href="device.html?id=${device.id}">Open</a>
          </div>
        </div>
      `,
    )
    .join("");
}

async function initDashboardPage() {
  bindConfigInputs();
  try {
    const [meta, devices] = await Promise.all([loadMeta(), loadDevices()]);
    setText("meta-host", meta.server.host);
    setText("meta-port", String(meta.server.port));
    setText("meta-ping", meta.server.ping_endpoint);
    setText("count-devices", String(devices.length));
    setText("count-connected", String(devices.filter((d) => d.connected).length));
    setText("count-video", String(countTracks(devices, "VIDEO")));
    setText("count-actions", String(coreActionsCount(devices)));
    setHtml("server-summary", `
      <div class="code">${escapeHtml(prettyJson(meta))}</div>
    `);
    renderDashboardDevices(devices);
  } catch (error) {
    setHtml("dashboard-error", `<div class="panel"><strong>Failed:</strong> ${escapeHtml(error.message)}</div>`);
  }
}

function renderDevicesTable(devices, filterText = "") {
  const body = document.getElementById("devices-body");
  if (!body) return;
  const q = filterText.trim().toLowerCase();
  const rows = devices.filter((device) => {
    if (!q) return true;
    return (
      device.name.toLowerCase().includes(q) ||
      String(device.id).includes(q) ||
      (device.main_video_track_name || "").toLowerCase().includes(q)
    );
  });
  if (!rows.length) {
    body.innerHTML = `
      <tr><td colspan="7" class="muted">No matching devices.</td></tr>
    `;
    return;
  }
  body.innerHTML = rows
    .map(
      (device) => `
        <tr>
          <td>${device.id}</td>
          <td>
            <strong>${escapeHtml(device.name)}</strong><br>
            <span class="muted">${escapeHtml(device.token)}</span>
          </td>
          <td>${statusBadge(device.connected)}</td>
          <td>${escapeHtml(device.main_video_track_name || "-")}</td>
          <td>${device.tracks.length}</td>
          <td>${escapeHtml(device.server.host)}:${device.server.port}</td>
          <td>
            <a class="button" href="device.html?id=${device.id}">Manage</a>
            <button class="button danger" data-delete-device="${device.id}">Delete</button>
          </td>
        </tr>
      `,
    )
    .join("");

  body.querySelectorAll("[data-delete-device]").forEach((button) => {
    button.addEventListener("click", async () => {
      const id = button.getAttribute("data-delete-device");
      if (!confirm(`Delete device ${id}?`)) return;
      await requestJson(`/devices/${id}`, { method: "DELETE" });
      await initDevicesPage();
    });
  });
}

async function initDevicesPage() {
  bindConfigInputs();
  const search = document.getElementById("device-search");
  try {
    const devices = await loadDevices();
    renderDevicesTable(devices, search ? search.value : "");
    if (search) {
      search.oninput = () => renderDevicesTable(devices, search.value);
    }
    const refresh = document.getElementById("refresh-devices");
    if (refresh) {
      refresh.onclick = async () => initDevicesPage();
    }
  } catch (error) {
    setHtml("devices-error", `<div class="panel"><strong>Failed:</strong> ${escapeHtml(error.message)}</div>`);
  }
}

function addTrackRow(container, initial = {}) {
  const row = document.createElement("div");
  row.className = "track-row";
  row.innerHTML = `
    <select data-track-field="type">
      ${[
        "VIDEO",
        "LIDAR",
        "AUDIO",
        "CONTROL",
        "BATTERY",
        "SPEAKER",
        "TOPIC",
        "MAP",
        "ODOMETRY",
        "GPS",
        "TRAJECTORY",
      ]
        .map((type) => `<option value="${type}" ${initial.type === type ? "selected" : ""}>${type}</option>`)
        .join("")}
    </select>
    <input data-track-field="name" placeholder="Track name" value="${escapeHtml(initial.name || "")}">
    <input data-track-field="endpoint" placeholder="Optional endpoint" value="${escapeHtml(initial.endpoint || "")}">
    <button type="button" class="button danger" data-remove-track>Remove</button>
  `;
  row.querySelector("[data-remove-track]").addEventListener("click", () => row.remove());
  container.appendChild(row);
}

function readTracks(container) {
  return Array.from(container.querySelectorAll(".track-row")).map((row) => {
    const type = row.querySelector("[data-track-field='type']").value;
    const name = row.querySelector("[data-track-field='name']").value.trim();
    const endpoint = row.querySelector("[data-track-field='endpoint']").value.trim();
    return endpoint ? { type, name, endpoint } : { type, name };
  });
}

function readActions(form) {
  const core = Array.from(form.querySelectorAll("[data-core-action]:checked")).map((node) => node.value);
  const customText = form.querySelector("[data-custom-actions]");
  const custom = customText
    ? customText.value
        .split(/[\n,]/)
        .map((value) => value.trim())
        .filter(Boolean)
    : [];
  return { core, custom };
}

async function initRegisterPage() {
  bindConfigInputs();
  const tracks = document.getElementById("tracks-container");
  if (tracks && !tracks.children.length) {
    addTrackRow(tracks, { type: "VIDEO", name: "video_main" });
    addTrackRow(tracks, { type: "CONTROL", name: "control" });
  }
  const addTrackButton = document.getElementById("add-track");
  if (addTrackButton) {
    addTrackButton.onclick = () => addTrackRow(tracks);
  }
  const form = document.getElementById("register-form");
  if (form) {
    form.onsubmit = async (event) => {
      event.preventDefault();
      const payload = {
        secretKey: getSecretKey(),
        name: form.querySelector("[name='name']").value.trim(),
        tracks: readTracks(tracks),
        actions: readActions(form),
      };
      try {
        const result = await requestJson("/devices", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        setHtml("register-result", `<div class="code">${escapeHtml(prettyJson(result))}</div>`);
        form.reset();
        tracks.innerHTML = "";
        addTrackRow(tracks, { type: "VIDEO", name: "video_main" });
        addTrackRow(tracks, { type: "CONTROL", name: "control" });
      } catch (error) {
        setHtml("register-result", `<div class="panel"><strong>Failed:</strong> ${escapeHtml(error.message)}</div>`);
      }
    };
  }
}

async function initDevicePage() {
  bindConfigInputs();
  const id = qs("id");
  if (!id) {
    setHtml("device-error", `<div class="panel">Missing <code>?id=</code> query parameter.</div>`);
    return;
  }
  const form = document.getElementById("device-edit-form");
  const mainTrackForm = document.getElementById("main-track-form");
  const deleteButton = document.getElementById("delete-device");
  try {
    const [device, meta] = await Promise.all([requestJson(`/devices/${id}`), loadMeta()]);
    setText("device-name", device.name);
    setText("device-id", String(device.id));
    setText("device-token", device.token);
    setText("device-status", device.connected ? "connected" : "disconnected");
    setText("device-created", formatTimestamp(device.created_at));
    setText("device-updated", formatTimestamp(device.updated_at));
    setText("device-main", device.main_video_track_name || "-");
    setHtml("device-json", `<div class="code">${escapeHtml(prettyJson(device))}</div>`);
    setHtml("device-tracks", renderEndpointList(device));
    setHtml("device-server", `<div class="code">${escapeHtml(prettyJson(device.server))}</div>`);

    if (form) {
      form.querySelector("[name='name']").value = device.name;
      form.onsubmit = async (event) => {
        event.preventDefault();
        await requestJson(`/devices/${id}`, {
          method: "PATCH",
          body: JSON.stringify({ name: form.querySelector("[name='name']").value }),
        });
        await initDevicePage();
      };
    }

    if (mainTrackForm) {
      const select = mainTrackForm.querySelector("[name='name']");
      const videoTracks = device.tracks.filter((track) => track.type === "VIDEO");
      select.innerHTML = videoTracks
        .map((track) => `<option value="${escapeHtml(track.name)}">${escapeHtml(track.name)}</option>`)
        .join("");
      if (device.main_video_track_name) {
        select.value = device.main_video_track_name;
      }
      mainTrackForm.querySelector(".helper").textContent =
        videoTracks.length
          ? `Detected VIDEO tracks from ${meta.server.host}:${meta.server.port}`
          : "No VIDEO track is available on this device.";
      mainTrackForm.onsubmit = async (event) => {
        event.preventDefault();
        await requestJson(`/devices/${id}/main-video-track`, {
          method: "PATCH",
          body: JSON.stringify({ name: select.value }),
        });
        await initDevicePage();
      };
    }

    if (deleteButton) {
      deleteButton.onclick = async () => {
        if (!confirm(`Delete device ${device.name}?`)) return;
        await requestJson(`/devices/${id}`, { method: "DELETE" });
        window.location.href = "devices.html";
      };
    }
  } catch (error) {
    setHtml("device-error", `<div class="panel"><strong>Failed:</strong> ${escapeHtml(error.message)}</div>`);
  }
}

async function initSettingsPage() {
  bindConfigInputs();
  try {
    const [health, meta] = await Promise.all([requestJson("/health"), loadMeta()]);
    setHtml("health-status", `<span class="badge ok">${escapeHtml(health.status)}</span>`);
    setHtml("meta-json", `<div class="code">${escapeHtml(prettyJson(meta))}</div>`);
    setText("settings-api-base-value", getApiBase());
  } catch (error) {
    setHtml("health-status", `<span class="badge danger">offline</span>`);
    setHtml("meta-json", `<div class="panel"><strong>Failed:</strong> ${escapeHtml(error.message)}</div>`);
  }
}

function initPage() {
  activeNav();
  const page = document.body.dataset.page;
  const map = {
    dashboard: initDashboardPage,
    devices: initDevicesPage,
    register: initRegisterPage,
    device: initDevicePage,
    settings: initSettingsPage,
  };
  const handler = map[page];
  if (handler) {
    handler();
  }
}

document.addEventListener("DOMContentLoaded", initPage);
