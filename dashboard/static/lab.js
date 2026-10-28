// Concurrency Lab front end: runs one experiment per button and draws the result.
"use strict";

(() => {

const $ = (id) => document.getElementById(id);
const fmt = (n) => Number(n).toLocaleString("en-IN");
let gilChart, semChart;

async function post(path, body = {}) {
  const res = await fetch(path, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

// Disable the button and show "Running…" while an experiment runs.
async function busy(button, msgEl, work) {
  const label = button.textContent;
  document.querySelectorAll("#pane-lab button").forEach((b) => (b.disabled = true));
  button.textContent = "Running…";
  msgEl.textContent = "";
  try {
    await work();
  } catch (err) {
    msgEl.textContent = err.message;
  } finally {
    button.textContent = label;
    document.querySelectorAll("#pane-lab button").forEach((b) => (b.disabled = false));
  }
}

// ------------------------------------------------------------ 1. race condition
function renderRace(r) {
  const box = $(r.use_lock ? "r-box-safe" : "r-box-unsafe");
  const ok = r.lost === 0;
  box.className = "result-box " + (ok ? "box-good" : "box-bad");
  box.innerHTML = `
    <div class="result-title">${r.use_lock ? "With lock" : "Without lock"}</div>
    <div class="result-big ${ok ? "text-success" : "text-danger"}">${fmt(r.actual)}</div>
    <div class="result-line">expected ${fmt(r.expected)} (${r.threads} threads × ${fmt(r.increments)})</div>
    <div class="result-line fw-semibold ${ok ? "text-success" : "text-danger"} mt-1">
      ${ok ? "Correct, no updates lost" : `${fmt(r.lost)} updates lost (${r.lost_percent}%)`}</div>
    <div class="result-line text-secondary mt-1">took ${r.seconds} s</div>`;
}

function runRace(useLock, button) {
  busy(button, $("r-msg"), async () => {
    renderRace(await post("/api/lab/race", {
      threads: $("r-threads").value, increments: $("r-incs").value, use_lock: useLock,
    }));
  });
}

// ------------------------------------------------------------ 2. GIL
function makeGilChart() {
  gilChart = new Chart($("g-chart"), {
    type: "bar",
    data: {
      labels: ["CPU-heavy work", "IO-heavy work"],
      datasets: [
        { label: "One after another", data: [], backgroundColor: "#adb5bd" },
        { label: "Threads", data: [], backgroundColor: "#0d6efd" },
        { label: "Processes", data: [], backgroundColor: "#e8710a" },
      ],
    },
    options: {
      maintainAspectRatio: false,
      scales: { y: { beginAtZero: true, title: { display: true, text: "seconds (lower is faster)" } },
                x: { grid: { display: false } } },
      plugins: { legend: { position: "top", align: "end", labels: { boxWidth: 10 } },
                 tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${c.raw} s` } } },
    },
  });
}

function speed(x) {
  if (x >= 0.9 && x < 1.1) return `about the same speed (${x}×)`;
  return x >= 1 ? `${x}× faster` : `${x}× (slower)`;
}

function renderGil(r) {
  const { cpu, io } = r;
  gilChart.data.datasets[0].data = [cpu.sequential, io.sequential];
  gilChart.data.datasets[1].data = [cpu.threads, io.threads];
  gilChart.data.datasets[2].data = [cpu.processes, io.processes];
  gilChart.update();

  $("g-info").textContent = `Python ${r.python} · ${r.cores} CPU cores · ${r.jobs} jobs, ${r.workers} workers · GIL ${r.gil_enabled ? "on" : "off"}`;

  const lines = [];
  if (r.gil_enabled && cpu.speedup_threads < 1.3) {
    lines.push(`<b>CPU work, threads: ${speed(cpu.speedup_threads)}.</b> No real gain: the GIL lets only one thread do maths at a time, and switching between them costs a little.`);
  } else {
    lines.push(`<b>CPU work, threads: ${speed(cpu.speedup_threads)}.</b>${r.gil_enabled ? "" : " This Python has no GIL, so threads can use several cores."}`);
  }
  if (cpu.speedup_processes >= 1.2) {
    lines.push(`<b>CPU work, processes: ${speed(cpu.speedup_processes)}.</b> Each process has its own Python and its own GIL, so they really use ${r.workers} cores at once (process start-up time is included).`);
  } else {
    lines.push(`<b>CPU work, processes: ${speed(cpu.speedup_processes)}.</b> Starting processes takes time; with bigger jobs they pull ahead.`);
  }
  lines.push(`<b>IO work, threads: ${speed(io.speedup_threads)}.</b> A waiting thread gives up the GIL, so the others keep going. That is why the scheduler uses threads: its jobs mostly wait on files and the disk.`);
  $("g-summary").innerHTML = lines.map((l) => `<li class="mb-1">${l}</li>`).join("");
}

// ------------------------------------------------------------ 3. semaphore
function makeSemChart() {
  semChart = new Chart($("s-chart"), {
    type: "bar",
    data: { labels: [], datasets: [
      { label: "Waiting for the semaphore", data: [], backgroundColor: "#dee2e6", grouped: false, barThickness: 16 },
      { label: "Using the resource", data: [], backgroundColor: "#0d6efd", grouped: false, barThickness: 16 },
    ] },
    options: {
      indexAxis: "y", maintainAspectRatio: false, animation: { duration: 400 },
      scales: { x: { beginAtZero: true, title: { display: true, text: "seconds since start" } },
                y: { grid: { display: false } } },
      plugins: { legend: { position: "top", align: "end", labels: { boxWidth: 10 } },
                 tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${c.raw[0]}–${c.raw[1]} s` } } },
    },
  });
}

function renderSem(r) {
  semChart.data.labels = r.rows.map((x) => x.thread);
  semChart.data.datasets[0].data = r.rows.map((x) => [x.asked, x.got]);
  semChart.data.datasets[1].data = r.rows.map((x) => [x.got, x.done]);
  semChart.update();
  const stat = (label, value, cls = "") =>
    `<div class="col-4"><div class="mini-label">${label}</div><div class="mini-value ${cls}">${value}</div></div>`;
  $("s-stats").innerHTML =
    stat("Limit", r.limit) +
    stat("Most at once", r.max_inside, r.max_inside <= r.limit ? "text-success" : "text-danger") +
    stat("Total time", r.total_seconds + " s");
}

function runSem(button) {
  busy(button, $("s-msg"), async () => {
    renderSem(await post("/api/lab/semaphore", { threads: $("s-threads").value, limit: $("s-limit").value }));
  });
}

// ------------------------------------------------------------ start
document.addEventListener("DOMContentLoaded", () => {
  Chart.defaults.font.size = 11;
  Chart.defaults.color = "#6c757d";
  makeGilChart();
  makeSemChart();
  $("r-unsafe").addEventListener("click", (e) => runRace(false, e.currentTarget));
  $("r-safe").addEventListener("click", (e) => runRace(true, e.currentTarget));
  $("g-run").addEventListener("click", (e) =>
    busy(e.currentTarget, $("g-msg"), async () => renderGil(await post("/api/lab/gil"))));
  $("s-run").addEventListener("click", (e) => runSem(e.currentTarget));

  // Tabs: open the lab from /#lab, keep the address in sync, and redraw the
  // charts when the tab is shown (a chart drawn while hidden has no size).
  const labTab = $("tab-lab"), dashTab = $("tab-dash");
  if (location.hash === "#lab") bootstrap.Tab.getOrCreateInstance(labTab).show();
  labTab.addEventListener("shown.bs.tab", () => {
    history.replaceState(null, "", "#lab");
    gilChart.resize();
    semChart.resize();
  });
  dashTab.addEventListener("shown.bs.tab", () => history.replaceState(null, "", location.pathname));
});
})();
