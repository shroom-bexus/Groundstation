"use strict";

const COLORS = {
  thermal_temperature: "#4dd9e8",
  thermal_target: "#ffac52",
  pads_temperature: "#5ba5ff",
  hids_temperature: "#a78bfa",
  pt1000_1: "#5cdf9a",
  pt1000_2: "#ec77c7",
  pt1000_3: "#f4d35e",
  pt1000_4: "#83b8ff",
  pt1000_5: "#b6e875",
  pt1000_6: "#d59cff",
  pt1000_7: "#ff8c82",
  pt1000_8: "#65e0bd",
  pt1000_9: "#d1d9e6",
  pressure: "#5ba5ff",
  thermal_output: "#ffac52",
  downlink: "#5cdf9a",
  uplink: "#a78bfa",
};

const LABELS = {
  thermal_temperature: "Thermal",
  thermal_target: "Target",
  pads_temperature: "PADS",
  hids_temperature: "HIDS",
  pressure: "Pressure",
  thermal_output: "PID output",
  downlink: "Downlink",
  uplink: "Uplink",
};
for (let i = 1; i <= 9; i += 1) LABELS[`pt1000_${i}`] = `TEMP ${i}`;

let lastState = null;
const hiddenTemperatureSeries = new Set();

function element(id) { return document.getElementById(id); }
function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
function valueOrDash(value, digits = 1) {
  return Number.isFinite(Number(value)) ? Number(value).toFixed(digits) : "—";
}
function formatDuration(seconds) {
  const total = Math.max(0, Math.floor(seconds || 0));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  return [hours, minutes, secs].map(value => String(value).padStart(2, "0")).join(":");
}

function visiblePoints(points, windowSeconds) {
  if (!points || !points.length) return [];
  const latest = points[points.length - 1][0];
  return points.filter(point => point[0] >= latest - windowSeconds);
}

function drawChart(canvas, sourceSeries, options = {}) {
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(320, canvas.clientWidth);
  const height = Math.max(150, canvas.clientHeight);
  if (canvas.width !== Math.floor(width * ratio) || canvas.height !== Math.floor(height * ratio)) {
    canvas.width = Math.floor(width * ratio);
    canvas.height = Math.floor(height * ratio);
  }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, width, height);

  const windowSeconds = Number(element("time-window").value);
  const series = Object.entries(sourceSeries)
    .map(([name, points]) => [name, visiblePoints(points, windowSeconds)])
    .filter(([, points]) => points.length);

  const pad = { left: 54, right: 14, top: 14, bottom: 28 };
  const plotWidth = width - pad.left - pad.right;
  const plotHeight = height - pad.top - pad.bottom;
  if (!series.length) {
    ctx.fillStyle = "#8291a7";
    ctx.font = "13px system-ui";
    ctx.fillText("Waiting for telemetry", pad.left, pad.top + 24);
    return;
  }

  const allPoints = series.flatMap(([, points]) => points);
  let xMax = Math.max(...allPoints.map(point => point[0]));
  let xMin = Math.max(0, xMax - windowSeconds);
  let yMin = options.yMin ?? Math.min(...allPoints.map(point => point[1]));
  let yMax = options.yMax ?? Math.max(...allPoints.map(point => point[1]));
  if (yMax === yMin) { yMin -= 1; yMax += 1; }
  const padding = (yMax - yMin) * 0.1;
  if (options.yMin === undefined) yMin -= padding;
  if (options.yMax === undefined) yMax += padding;

  const xScale = x => pad.left + ((x - xMin) / Math.max(1, xMax - xMin)) * plotWidth;
  const yScale = y => pad.top + (1 - (y - yMin) / (yMax - yMin)) * plotHeight;

  ctx.lineWidth = 1;
  ctx.strokeStyle = "rgba(118, 151, 189, 0.13)";
  ctx.fillStyle = "#8291a7";
  ctx.font = "11px ui-monospace, monospace";
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  for (let index = 0; index <= 4; index += 1) {
    const y = pad.top + (plotHeight * index) / 4;
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(width - pad.right, y); ctx.stroke();
    const value = yMax - ((yMax - yMin) * index) / 4;
    ctx.fillText(options.formatY ? options.formatY(value) : value.toFixed(1), pad.left - 8, y);
  }
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  for (let index = 0; index <= 4; index += 1) {
    const x = pad.left + (plotWidth * index) / 4;
    const secondsAgo = Math.round(xMax - (xMin + ((xMax - xMin) * index) / 4));
    ctx.fillText(secondsAgo === 0 ? "now" : `−${secondsAgo}s`, x, height - pad.bottom + 9);
  }

  for (const [name, points] of series) {
    ctx.strokeStyle = COLORS[name] || "#d1d9e6";
    ctx.lineWidth = name === "thermal_target" ? 1.5 : 2;
    ctx.setLineDash(name === "thermal_target" ? [5, 5] : []);
    ctx.beginPath();
    points.forEach((point, index) => {
      const x = xScale(point[0]);
      const y = yScale(point[1]);
      if (index === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.stroke();
  }
  ctx.setLineDash([]);
}

function updateLegend(names) {
  const legend = element("temperature-legend");
  legend.innerHTML = names.map(name => `
    <button class="legend-item" type="button" data-series="${name}" aria-pressed="${!hiddenTemperatureSeries.has(name)}">
      <span class="legend-swatch" style="background:${COLORS[name]}"></span>${LABELS[name]}
    </button>`).join("");
  legend.querySelectorAll(".legend-item").forEach(button => {
    button.addEventListener("click", () => {
      const name = button.dataset.series;
      if (hiddenTemperatureSeries.has(name)) hiddenTemperatureSeries.delete(name);
      else hiddenTemperatureSeries.add(name);
      if (lastState) updateState(lastState);
    });
  });
}

function updateHealth(health) {
  const entries = Object.entries(health || {}).sort(([a], [b]) => a.localeCompare(b, undefined, { numeric: true }));
  if (!entries.length) return;
  const faults = entries.filter(([, item]) => !["OK", "VALID"].includes(item.state)).length;
  element("health-summary").textContent = faults ? `${faults} attention` : "All nominal";
  element("health-summary").style.color = faults ? "#ff667a" : "#5cdf9a";
  element("health-list").classList.remove("empty-state");
  element("health-list").innerHTML = entries.map(([key, item]) => {
    const fault = !["OK", "VALID"].includes(item.state);
    let detail = `errors ${item.error_count ?? 0}`;
    if (item.last_message_age_ms !== undefined) detail = `last ${(item.last_message_age_ms / 1000).toFixed(1)} s · overflows ${item.overflow_count}`;
    if (item.fault !== undefined) detail = `fault ${item.fault} · errors ${item.error_count}`;
    return `<div class="health-item"><div class="health-name"><span>${escapeHtml(key.replace("_", " "))}</span><span class="state ${fault ? "fault" : ""}">${escapeHtml(item.state)}</span></div><div class="health-detail">${escapeHtml(detail)}</div></div>`;
  }).join("");
}

function updateAirdos(state) {
  const latest = state.latest.airdos || {};
  const keys = Object.keys(latest).sort((a, b) => Number(a) - Number(b));
  if (!keys.length) return;
  element("airdos-list").classList.remove("empty-state");
  element("airdos-list").innerHTML = keys.map(sensor => `
    <div class="airdos-item">
      <div class="airdos-name"><span>Sensor ${escapeHtml(sensor)}</span><span class="state">${state.airdos_counts[sensor] || 0} received</span></div>
      <div class="airdos-detail">${escapeHtml(latest[sensor].data)}</div>
    </div>`).join("");
}

function updateLogs(logs) {
  if (!logs || !logs.length) return;
  const recent = logs.slice(-12).reverse();
  element("log-list").classList.remove("empty-state");
  element("log-list").innerHTML = recent.map(item => `
    <div class="log-line"><span class="log-time">${formatDuration(item.time_s)}</span><span class="log-message"></span></div>`).join("");
  [...element("log-list").querySelectorAll(".log-message")].forEach((node, index) => {
    node.textContent = recent[index].message;
  });
}

function updateState(state) {
  lastState = state;
  const latest = state.latest || {};
  const thermal = latest.thermal || {};
  const pads = latest.pads || {};
  const hids = latest.hids || {};
  const downlink = latest.downlink || {};

  element("connection-pill").classList.toggle("online", state.connected);
  element("connection-pill").classList.toggle("offline", !state.connected);
  element("connection-text").textContent = state.connected ? "ONLINE" : "OFFLINE";
  element("mission-time").textContent = formatDuration(state.elapsed_s);
  element("last-update").textContent = new Date().toLocaleTimeString([], { hour12: false });

  element("thermal-temperature").textContent = valueOrDash(thermal.temperature_k, 2);
  element("thermal-target").textContent = `Target ${valueOrDash(thermal.target_k, 2)} K`;
  element("pressure-value").textContent = valueOrDash(Number(pads.pressure_pa) / 100, 1);
  element("pads-temperature").textContent = `PADS ${valueOrDash(pads.temperature_k, 2)} K`;
  element("humidity-value").textContent = valueOrDash(hids.humidity_percent, 1);
  element("hids-temperature").textContent = `HIDS ${valueOrDash(hids.temperature_k, 2)} K`;
  element("heater-output").textContent = valueOrDash(thermal.output_percent, 1);
  element("pid-state").textContent = `PID ${thermal.controller_enabled === true ? "ON" : thermal.controller_enabled === false ? "OFF" : "—"}`;
  element("downlink-rate").textContent = valueOrDash(state.rates.download_kbit_s, 1);
  const dlLimit = state.rates.download_limit_kbit_s === 0 ? "unlimited" : `${valueOrDash(state.rates.download_limit_kbit_s, 1)} kbit/s`;
  element("downlink-limit").textContent = `Limit ${dlLimit}`;
  element("heater-mode").textContent = thermal.controller_enabled ? `PID · ${valueOrDash(thermal.output_percent, 1)}%` : "Manual / off";
  element("pressure-delta").textContent = `${valueOrDash(Number(pads.pressure_pa) / 100, 1)} hPa`;
  element("link-summary").textContent = `↑ ${valueOrDash(state.rates.upload_kbit_s, 2)} · ↓ ${valueOrDash(state.rates.download_kbit_s, 2)} kbit/s`;

  const selected = downlink.airdos_selected_count;
  element("airdos-selection").textContent = selected === undefined ? "— / 9" : `${selected} / 9 · level ${downlink.airdos_level}`;
  element("system-queue").textContent = downlink.system_queue ?? "—";
  element("airdos-queue").textContent = downlink.airdos_queue ?? "—";
  element("drop-count").textContent = downlink.drop_count ?? "—";
  element("suppressed-count").textContent = downlink.suppressed_count ?? "—";
  const queueTotal = (downlink.system_queue || 0) + (downlink.airdos_queue || 0);
  element("queue-level").textContent = downlink.system_queue === undefined ? "—" : `${queueTotal} pending`;

  updateHealth(state.health);
  updateAirdos(state);
  updateLogs(state.logs);

  const temperatureNames = ["thermal_temperature", "thermal_target", "pads_temperature", "hids_temperature"];
  for (let sensor = 1; sensor <= 9; sensor += 1) {
    if (state.series[`pt1000_${sensor}`]) temperatureNames.push(`pt1000_${sensor}`);
  }
  updateLegend(temperatureNames);
  const visibleTemperatureNames = temperatureNames.filter(name => !hiddenTemperatureSeries.has(name));
  drawChart(element("temperature-chart"), Object.fromEntries(visibleTemperatureNames.map(name => [name, state.series[name] || []])), { formatY: value => value.toFixed(1) });
  drawChart(element("pressure-chart"), { pressure: state.series.pressure || [] }, { formatY: value => (value / 100).toFixed(0) });
  drawChart(element("output-chart"), { thermal_output: state.series.thermal_output || [] }, { yMin: 0, yMax: 100, formatY: value => `${value.toFixed(0)}%` });
  drawChart(element("link-chart"), { uplink: state.series.uplink || [], downlink: state.series.downlink || [] }, { yMin: 0, formatY: value => value.toFixed(1) });
}

async function refresh() {
  try {
    const response = await fetch("/api/state", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    updateState(await response.json());
  } catch (error) {
    element("connection-pill").classList.remove("online");
    element("connection-text").textContent = "DASHBOARD LOST";
  }
}

element("time-window").addEventListener("change", () => {
  if (lastState) updateState(lastState);
});
window.addEventListener("resize", () => {
  if (lastState) updateState(lastState);
});

refresh();
setInterval(refresh, 1000);
