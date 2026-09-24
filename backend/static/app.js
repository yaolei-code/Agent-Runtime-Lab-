const state = {
  currentRunId: null,
};

const messages = document.querySelector("#messages");
const form = document.querySelector("#chat-form");
const input = document.querySelector("#chat-input");
const statusEl = document.querySelector("#run-status");

function setStatus(status) {
  statusEl.textContent = status;
  statusEl.className = `status ${status}`;
}

function addMessage(role, content) {
  const card = document.createElement("div");
  card.className = `message ${role}`;
  card.innerHTML = `<div class="role">${role}</div><div>${escapeHtml(content)}</div>`;
  messages.appendChild(card);
  messages.scrollTop = messages.scrollHeight;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail);
  }
  return response.json();
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  addMessage("user", text);
  setStatus("running");

  try {
    const result = await api("/chat", {
      method: "POST",
      body: JSON.stringify({ message: text }),
    });
    handleRunResult(result);
  } catch (error) {
    setStatus("failed");
    addMessage("assistant", error.message);
  }
});

function handleRunResult(result) {
  state.currentRunId = result.run_id;
  setStatus(result.status);
  if (result.status === "waiting_for_approval") {
    addMessage("assistant", `Waiting for approval: ${result.approval_id}`);
    switchTab("approvals");
    refreshApprovals();
  } else if (result.answer) {
    addMessage("assistant", result.answer);
  }
  renderTrace(result.trace || []);
  loadRun(result.run_id).catch((error) => console.error(error));
  refreshRuns();
  refreshMemory();
}

function switchTab(name) {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.tab === name);
  });
  document.querySelectorAll(".panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === name);
  });
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => switchTab(tab.dataset.tab));
});

document.querySelector("#refresh-trace").addEventListener("click", refreshTrace);
document.querySelector("#refresh-runs").addEventListener("click", refreshRuns);
document.querySelector("#refresh-memory").addEventListener("click", refreshMemory);
document.querySelector("#refresh-approvals").addEventListener("click", refreshApprovals);
document.querySelector("#refresh-tools").addEventListener("click", refreshTools);

async function refreshTrace() {
  if (!state.currentRunId) {
    renderRunDetail(null);
    renderTrace([]);
    return;
  }
  await loadRun(state.currentRunId);
}

function renderRunDetail(detail) {
  const container = document.querySelector("#run-detail");
  if (!detail) {
    container.className = "run-detail empty";
    container.textContent = "No run selected.";
    return;
  }

  const pendingApproval = detail.pending_approval
    ? `${detail.pending_approval.approval_id} (${detail.pending_approval.status})`
    : "None";

  container.className = "run-detail";
  container.innerHTML = `
    <div class="run-detail-head">
      <div>
        <div class="label">run_id</div>
        <strong>${escapeHtml(detail.run_id)}</strong>
      </div>
      <span class="status ${escapeHtml(detail.status)}">${escapeHtml(detail.status)}</span>
    </div>
    <div class="detail-grid">
      <div class="label">input</div><div>${escapeHtml(detail.user_input)}</div>
      <div class="label">answer</div><div>${escapeHtml(detail.answer || "")}</div>
      <div class="label">steps</div><div>${escapeHtml(detail.steps)}</div>
      <div class="label">pending_approval</div><div>${escapeHtml(pendingApproval)}</div>
      <div class="label">created_at</div><div>${escapeHtml(detail.created_at)}</div>
    </div>`;
}

async function loadRun(runId, options = {}) {
  const detail = await api(`/runs/${runId}`);
  state.currentRunId = detail.run_id;
  setStatus(detail.status);
  renderRunDetail(detail);
  renderTrace(await api(`/traces/${detail.run_id}`));
  if (options.switchToTrace) {
    switchTab("trace");
  }
  refreshRuns();
}

function eventTitle(type) {
  return String(type || "event")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function eventTone(event) {
  const type = String(event.type || "");
  if (type.includes("failed") || type.includes("error")) return "error";
  if (type.includes("approval")) return "approval";
  if (type.includes("tool")) return "tool";
  if (type.includes("llm")) return "llm";
  if (type.includes("memory")) return "memory";
  if (type.includes("completed") || type.includes("final")) return "final";
  return "default";
}

function eventSummary(event) {
  const payload = event.payload || {};
  switch (event.type) {
    case "run_started":
      return `Input: ${payload.user_input || ""}`;
    case "memory_retrieved":
      return `${payload.count ?? 0} memories retrieved`;
    case "llm_request":
      return `Sent ${payload.message_count ?? 0} messages with ${payload.tool_count ?? 0} tools`;
    case "llm_response":
      return `Model action: ${payload.action || "unknown"}`;
    case "tool_requested":
      return `${payload.tool_name || "tool"} ${JSON.stringify(payload.arguments || {})}`;
    case "tool_started":
      return `${payload.tool_name || "tool"} started`;
    case "tool_completed":
      return `${payload.tool_name || "tool"} returned ${JSON.stringify(payload.result)}`;
    case "tool_failed":
      return `${payload.tool_name || "tool"} failed: ${payload.error || payload.reason || ""}`;
    case "approval_requested":
      return `${payload.tool_name || "tool"} requires approval (${payload.risk_level || "unknown"})`;
    case "approval_resolved":
      return `${payload.tool_name || "tool"} ${payload.status || "resolved"}`;
    case "memory_written":
      return `Memory written: ${payload.memory_id || ""}`;
    case "run_completed":
      return `Answer: ${payload.answer || ""}`;
    case "run_failed":
      return payload.error || "Run failed";
    default:
      return JSON.stringify(payload);
  }
}

function renderTrace(events) {
  const container = document.querySelector("#trace-list");
  if (!events.length) {
    container.innerHTML = `<div class="row">No trace selected.</div>`;
    return;
  }
  container.innerHTML = events
    .map(
      (event) => `
      <article class="timeline-item ${escapeHtml(eventTone(event))}">
        <div class="timeline-marker"></div>
        <div class="timeline-body">
          <div class="timeline-head">
            <strong>${escapeHtml(eventTitle(event.type))}</strong>
            <span class="label">${escapeHtml(event.timestamp || "")}</span>
          </div>
          <div class="event-summary">${escapeHtml(eventSummary(event))}</div>
          <details>
            <summary>Payload</summary>
            <pre>${escapeHtml(JSON.stringify(event.payload, null, 2))}</pre>
          </details>
        </div>
      </article>`
    )
    .join("");
}

async function refreshRuns() {
  const items = await api("/runs");
  const container = document.querySelector("#run-list");
  if (!items.length) {
    container.innerHTML = `<div class="row">No runs yet.</div>`;
    return;
  }
  container.innerHTML = items
    .map(
      (item) => `
      <article class="row ${item.run_id === state.currentRunId ? "selected" : ""}">
        <div class="row-grid">
          <div class="label">status</div><div>${escapeHtml(item.status)}</div>
          <div class="label">input</div><div>${escapeHtml(item.user_input)}</div>
          <div class="label">answer</div><div>${escapeHtml(item.answer || "")}</div>
          <div class="label">steps</div><div>${escapeHtml(item.steps)}</div>
          <div class="label">created_at</div><div>${escapeHtml(item.created_at)}</div>
        </div>
        <div class="actions">
          <button data-open-run="${escapeHtml(item.run_id)}">Open</button>
        </div>
      </article>`
    )
    .join("");

  container.querySelectorAll("[data-open-run]").forEach((button) => {
    button.addEventListener("click", async () => {
      await loadRun(button.dataset.openRun, { switchToTrace: true });
    });
  });
}

async function refreshMemory() {
  const items = await api("/memory");
  const container = document.querySelector("#memory-list");
  if (!items.length) {
    container.innerHTML = `<div class="row">No long-term memory yet.</div>`;
    return;
  }
  container.innerHTML = items
    .map(
      (item) => `
      <article class="row">
        <div class="row-grid">
          <div class="label">type</div><div>${escapeHtml(item.type)}</div>
          <div class="label">content</div><div>${escapeHtml(item.content)}</div>
          <div class="label">source</div><div>${escapeHtml(item.source)}</div>
          <div class="label">created_at</div><div>${escapeHtml(item.created_at)}</div>
        </div>
        <div class="actions">
          <button class="danger" data-delete-memory="${escapeHtml(item.id)}">Delete</button>
        </div>
      </article>`
    )
    .join("");
  container.querySelectorAll("[data-delete-memory]").forEach((button) => {
    button.addEventListener("click", async () => {
      await fetch(`/memory/${button.dataset.deleteMemory}`, { method: "DELETE" });
      refreshMemory();
    });
  });
}

async function refreshApprovals() {
  const items = await api("/approvals");
  const container = document.querySelector("#approval-list");
  if (!items.length) {
    container.innerHTML = `<div class="row">No pending approvals.</div>`;
    return;
  }
  container.innerHTML = items
    .map(
      (item) => `
      <article class="row">
        <div class="row-grid">
          <div class="label">tool</div><div>${escapeHtml(item.tool_call.tool_name)}</div>
          <div class="label">arguments</div><pre>${escapeHtml(JSON.stringify(item.tool_call.arguments, null, 2))}</pre>
          <div class="label">risk</div><div>${escapeHtml(item.risk.risk_level)} - ${escapeHtml(item.risk.reason)}</div>
          <div class="label">run_id</div><div>${escapeHtml(item.run_id)}</div>
        </div>
        <div class="actions">
          <button data-approve="${escapeHtml(item.approval_id)}">Approve</button>
          <button class="danger" data-reject="${escapeHtml(item.approval_id)}">Reject</button>
        </div>
      </article>`
    )
    .join("");

  container.querySelectorAll("[data-approve]").forEach((button) => {
    button.addEventListener("click", async () => {
      setStatus("running");
      const result = await api(`/approvals/${button.dataset.approve}/approve`, { method: "POST" });
      handleRunResult(result);
      refreshApprovals();
    });
  });
  container.querySelectorAll("[data-reject]").forEach((button) => {
    button.addEventListener("click", async () => {
      setStatus("running");
      const result = await api(`/approvals/${button.dataset.reject}/reject`, { method: "POST" });
      handleRunResult(result);
      refreshApprovals();
    });
  });
}

async function refreshTools() {
  const items = await api("/tools");
  const container = document.querySelector("#tool-list");
  container.innerHTML = items
    .map(
      (item) => `
      <article class="row">
        <div class="row-grid">
          <div class="label">name</div><div>${escapeHtml(item.name)}</div>
          <div class="label">description</div><div>${escapeHtml(item.description)}</div>
          <div class="label">risk_level</div><div>${escapeHtml(item.risk_level)}</div>
        </div>
      </article>`
    )
    .join("");
}

refreshTools();
refreshRuns();
refreshMemory();
refreshApprovals();
renderRunDetail(null);
renderTrace([]);
