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
    renderTrace([]);
    return;
  }
  renderTrace(await api(`/traces/${state.currentRunId}`));
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
      <article class="event">
        <strong>${escapeHtml(event.type)}</strong>
        <div class="label">${escapeHtml(event.timestamp || "")}</div>
        <pre>${escapeHtml(JSON.stringify(event.payload, null, 2))}</pre>
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
      const detail = await api(`/runs/${button.dataset.openRun}`);
      state.currentRunId = detail.run_id;
      setStatus(detail.status);
      renderTrace(await api(`/traces/${detail.run_id}`));
      switchTab("trace");
      refreshRuns();
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
renderTrace([]);
