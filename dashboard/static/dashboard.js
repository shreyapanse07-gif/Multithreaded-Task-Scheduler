// Dashboard front end: polls the Flask JSON API and redraws the page.
"use strict";

const POLL_MS = 2000;
const STATUS_ORDER = ["PENDING", "SCHEDULED", "RUNNING", "RETRYING", "SUCCESS", "FAILED", "CANCELLED"];
const STATUS_COLORS = {
  PENDING: "#adb5bd", SCHEDULED: "#6f9ed6", RUNNING: "#0d6efd", RETRYING: "#e0a800",
  SUCCESS: "#198754", FAILED: "#dc3545", CANCELLED: "#6c757d",
};
const BADGE = {
  PENDING: "text-bg-light border", SCHEDULED: "text-bg-info", RUNNING: "text-bg-primary",
  RETRYING: "text-bg-warning", SUCCESS: "text-bg-success", FAILED: "text-bg-danger",
  CANCELLED: "text-bg-secondary",
};
const CANCELLABLE = ["PENDING", "SCHEDULED", "RETRYING"];
const FINISHED = ["SUCCESS", "FAILED", "CANCELLED"];

const $ = (id) => document.getElementById(id);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

let jobs = [];
let sysChart, statusChart, modal;

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" }, ...options,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error || `Request failed (${res.status})`);
  return body;
}

function setLive(ok) {
  $("live-dot").className = "dot " + (ok ? "dot-on" : "dot-off");
  $("live-text").textContent = ok ? "live" : "not connected";
}

// ---------------------------------------------------------------- charts
function makeCharts() {
  Chart.defaults.font.size = 11;
  Chart.defaults.color = "#6c757d";
  sysChart = new Chart($("sys-chart"), {
    type: "line",
    data: { labels: [], datasets: [
      { label: "CPU %", data: [], borderColor: "#0d6efd", backgroundColor: "#0d6efd", borderWidth: 1.5, pointRadius: 0, tension: 0.25 },
      { label: "Memory %", data: [], borderColor: "#e8710a", backgroundColor: "#e8710a", borderWidth: 1.5, pointRadius: 0, tension: 0.25 },
    ] },
    options: {
      animation: false, maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
      scales: { y: { min: 0, max: 100, ticks: { callback: (v) => v + "%" } },
                x: { ticks: { maxTicksLimit: 8 }, grid: { display: false } } },
      plugins: { legend: { position: "top", align: "end", labels: { boxWidth: 10 } } },
    },
  });
  statusChart = new Chart($("status-chart"), {
    type: "bar",
    data: { labels: STATUS_ORDER, datasets: [{ data: [], backgroundColor: STATUS_ORDER.map((s) => STATUS_COLORS[s]), barThickness: 14 }] },
    options: {
      indexAxis: "y", animation: false, maintainAspectRatio: false,
      scales: { x: { beginAtZero: true, ticks: { precision: 0 } }, y: { grid: { display: false } } },
      plugins: { legend: { display: false } },
    },
  });
}

// ---------------------------------------------------------------- renderers
function renderStats(data) {
  const c = data.counts;
  $("c-total").textContent = data.total;
  $("c-waiting").textContent = c.PENDING + c.SCHEDULED + c.RETRYING;
  $("c-running").textContent = c.RUNNING;
  $("c-success").textContent = c.SUCCESS;
  $("c-failed").textContent = c.FAILED;
  $("c-retried").textContent = data.stats.retried;
  $("q-size").textContent = data.stats.queued;
  $("w-size").textContent = data.stats.waiting;
  $("avg-dur").textContent = data.avg_duration == null ? "–" : data.avg_duration + " s";

  $("workers").innerHTML = data.workers.map((w) => `
    <li class="list-group-item d-flex justify-content-between align-items-center">
      <div><div class="fw-semibold">${esc(w.name)}</div>
        <div class="small text-secondary truncate">${w.current_task ? esc(w.current_task) : "waiting for work"}</div></div>
      <div class="text-end"><span class="badge ${w.state === "busy" ? "text-bg-primary" : "text-bg-light border"}">${w.state}</span>
        <div class="small text-secondary">${w.tasks_done} done</div></div>
    </li>`).join("");

  statusChart.data.datasets[0].data = STATUS_ORDER.map((s) => c[s] || 0);
  statusChart.update();
}

function renderSystem(data) {
  const s = data.latest;
  if (s) {
    $("sys-time").textContent = "· updated " + s.time;
    $("s-cpu").textContent = s.cpu_percent.toFixed(0) + "%";
    $("s-mem").textContent = s.memory_percent.toFixed(0) + "%";
    $("s-mem-sub").textContent = `${s.memory_used_gb} / ${s.memory_total_gb} GB`;
    $("s-disk").textContent = s.disk_percent.toFixed(0) + "%";
    $("s-disk-sub").textContent = `${s.disk_free_gb} GB free`;
    $("s-up").textContent = s.uptime;
    $("s-proc").textContent = `${s.processes} processes` +
      (s.battery_percent != null ? ` · battery ${s.battery_percent}%` : "");
  }
  sysChart.data.labels = data.history.map((h) => h.time);
  sysChart.data.datasets[0].data = data.history.map((h) => h.cpu);
  sysChart.data.datasets[1].data = data.history.map((h) => h.memory);
  sysChart.update();

  $("proc-rows").innerHTML = data.processes.map((p) => `
    <tr><td class="truncate">${esc(p.name)}</td><td>${p.pid}</td>
      <td class="text-end">${p.memory_mb.toFixed(1)} MB</td><td class="text-end">${p.cpu_percent.toFixed(1)}%</td></tr>`).join("")
    || `<tr><td colspan="4" class="text-secondary">Collecting…</td></tr>`;
}

function timeCell(t) {
  if (t.status === "SCHEDULED" || t.status === "RETRYING") return `at ${t.run_at}`;
  if (t.status === "RUNNING") return `since ${t.started_at}`;
  return fmtSeconds(t.duration);
}

function fmtSeconds(sec) {
  if (sec == null) return "–";
  sec = Number(sec);
  return sec < 1 ? `${Math.max(1, Math.round(sec * 1000))} ms` : `${sec.toFixed(2)} s`;
}

function renderTasks(tasks) {
  if (!tasks.length) {
    $("task-rows").innerHTML = `<tr><td colspan="7" class="text-secondary">No tasks</td></tr>`;
    return;
  }
  $("task-rows").innerHTML = tasks.map((t) => `
    <tr>
      <td><div class="truncate fw-semibold" title="${esc(t.name)}">${esc(t.name)}</div>
          <div class="small text-secondary truncate">${t.param ? esc(t.param) : (t.interval ? `every ${t.interval}s` : "&nbsp;")}</div></td>
      <td>${esc(t.priority_name)}</td>
      <td><span class="badge ${BADGE[t.status] || ""}">${t.status}</span></td>
      <td class="text-nowrap">${esc(t.worker || "–")}</td>
      <td>${t.retries}/${t.max_retries}</td>
      <td class="text-nowrap">${timeCell(t)}</td>
      <td class="text-end text-nowrap">
        <button class="btn btn-link btn-sm p-0 me-2" data-detail="${t.id}">Details</button>
        ${CANCELLABLE.includes(t.status) ? `<button class="btn btn-link btn-sm p-0 text-danger" data-cancel="${t.id}">Cancel</button>` : ""}
        ${FINISHED.includes(t.status) && t.job ? `<button class="btn btn-link btn-sm p-0" data-rerun="${t.id}">Run again</button>` : ""}
      </td>
    </tr>`).join("");
}

function renderHistory(rows) {
  $("history-rows").innerHTML = rows.map((r) => `
    <tr><td class="truncate">${esc(r.name)}</td><td class="text-nowrap">${esc(r.worker)}</td>
      <td>${esc((r.started_at || "").slice(11, 19))}</td>
      <td class="text-end">${fmtSeconds(r.duration)}</td>
      <td><span class="badge ${BADGE[String(r.status).toUpperCase()] || "text-bg-light border"}">${esc(r.status)}</span></td>
      <td class="truncate text-danger" title="${esc(r.error)}">${esc(r.error || "")}</td></tr>`).join("")
    || `<tr><td colspan="6" class="text-secondary">Nothing has run yet</td></tr>`;
}

// ---------------------------------------------------------------- polling
async function refresh() {
  try {
    const filter = $("status-filter").value;
    const [stats, system, tasks] = await Promise.all([
      api("/api/stats"), api("/api/system"),
      api("/api/tasks" + (filter ? "?status=" + filter : "")),
    ]);
    renderStats(stats);
    renderSystem(system);
    renderTasks(tasks);
    setLive(true);
  } catch (err) {
    setLive(false);
  }
}

async function refreshHistory() {
  try { renderHistory(await api("/api/history")); } catch (err) { /* shown by live dot */ }
}

// ---------------------------------------------------------------- form + actions
function showMessage(text, ok) {
  const el = $("form-msg");
  el.className = "small mt-2 " + (ok ? "text-success" : "text-danger");
  el.textContent = text;
}

function updateParamField() {
  const job = jobs.find((j) => j.key === $("f-job").value);
  const needs = job && job.param;
  $("param-row").classList.toggle("d-none", !needs);
  $("f-param").required = Boolean(needs);
  if (needs) {
    $("param-label").textContent = job.param;
    $("f-param").placeholder = job.param.startsWith("Folder")
      ? "e.g. C:\\Users\\you\\Downloads" : "e.g. C:\\Users\\you\\notes.txt";
  }
}

async function submitTask(event) {
  event.preventDefault();
  const body = {
    job: $("f-job").value,
    param: $("f-param").value,
    name: $("f-name").value,
    priority: document.querySelector("input[name=priority]:checked").value,
    delay: $("f-delay").value,
    max_retries: $("f-retries").value,
    interval: $("f-interval").value,
  };
  try {
    const task = await api("/api/tasks", { method: "POST", body: JSON.stringify(body) });
    showMessage(`Submitted "${task.name}"`, true);
    $("f-name").value = "";
    refresh();
  } catch (err) {
    showMessage(err.message, false);
  }
}

async function showDetails(id) {
  const { task, attempts } = await api("/api/tasks/" + id);
  $("detail-title").textContent = task.name;
  const fields = [
    ["Status", `<span class="badge ${BADGE[task.status]}">${task.status}</span>`],
    ["Job", esc(task.job || "–")], ["Input", esc(task.param || "–")],
    ["Priority", esc(task.priority_name)], ["Worker", esc(task.worker || "–")],
    ["Retries", `${task.retries} of ${task.max_retries}`],
    ["Created", task.created_at], ["Started", task.started_at || "–"],
    ["Finished", task.finished_at || "–"],
    ["Duration", fmtSeconds(task.duration)],
    ["Repeats", task.interval ? `every ${task.interval} s` : "no"],
    ["IO task (semaphore)", task.is_io ? "yes" : "no"],
  ];
  $("detail-body").innerHTML = `
    <dl class="row small mb-3">${fields.map(([k, v]) => `<dt class="col-sm-4 text-secondary fw-normal">${k}</dt><dd class="col-sm-8">${v}</dd>`).join("")}</dl>
    ${task.error ? `<div class="alert alert-danger small py-2">${esc(task.error)}</div>` : ""}
    <h6 class="small fw-semibold">Result</h6>
    <pre class="result">${task.result == null ? "–" : esc(JSON.stringify(task.result, null, 2))}</pre>
    <h6 class="small fw-semibold mt-3">Attempts</h6>
    <table class="table table-sm"><thead><tr><th>Worker</th><th>Started</th><th>Duration</th><th>Status</th><th>Error</th></tr></thead>
    <tbody>${attempts.map((a) => `<tr><td>${esc(a.worker)}</td><td>${esc((a.started_at || "").slice(11, 19))}</td>
      <td>${fmtSeconds(a.duration)}</td><td>${esc(a.status)}</td>
      <td class="text-danger">${esc(a.error || "")}</td></tr>`).join("") || `<tr><td colspan="5" class="text-secondary">Not run yet</td></tr>`}</tbody></table>`;
  modal.show();
}

async function onTableClick(event) {
  const btn = event.target.closest("button");
  if (!btn) return;
  try {
    if (btn.dataset.detail) await showDetails(btn.dataset.detail);
    if (btn.dataset.cancel) { await api(`/api/tasks/${btn.dataset.cancel}/cancel`, { method: "POST" }); refresh(); }
    if (btn.dataset.rerun) { await api(`/api/tasks/${btn.dataset.rerun}/rerun`, { method: "POST" }); refresh(); }
  } catch (err) {
    alert(err.message);
  }
}

// ---------------------------------------------------------------- start
async function init() {
  modal = new bootstrap.Modal($("detail-modal"));
  makeCharts();
  jobs = await api("/api/jobs");
  $("f-job").innerHTML = jobs.map((j) => `<option value="${j.key}">${esc(j.label)}</option>`).join("");
  $("f-job").addEventListener("change", updateParamField);
  updateParamField();
  $("task-form").addEventListener("submit", submitTask);
  $("status-filter").addEventListener("change", refresh);
  $("task-rows").addEventListener("click", onTableClick);

  refresh();
  refreshHistory();
  setInterval(refresh, POLL_MS);
  setInterval(refreshHistory, POLL_MS * 2);
}

document.addEventListener("DOMContentLoaded", init);
