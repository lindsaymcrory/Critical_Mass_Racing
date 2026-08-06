#!/usr/bin/env python3

# Copyright 2026 Lindsay McRory
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Renders one race's Vakaros Analysis page: course plot + maneuver log,
built entirely from that race's Vakaros GPS-track CSV (build_vakaros_db.py)
-- a completely separate data source and page from the EBL/N2K Race Results
page (render_race_page.py), reusing only its visual style. No polar or fleet
comparison section here (Vakaros logs no wind data, so no polar target
comparison is possible), and no trim slider (the track is already trimmed to
the race's established gun-to-finish window from races.json)."""
import json
from pathlib import Path

import build_vakaros_db
import vakaros_registry

ROOT = Path(__file__).parent
VAKAROS_DIR = ROOT / "vakaros"

PAGE_TEMPLATE = """<title>__TITLE__ — Vakaros Analysis</title>
<style>
  :root {
    --ink: #0a1a20; --panel: #122a32; --panel-2: #0e222a;
    --grid: #1f3e48; --grid-strong: #2a4e59; --paper: #e7ede9;
    --dim: #7fa3ab; --dim-2: #547881;
    --mark: #f5b942; --maneuver: #5aa7e0;
    --hair: #24444f; --radius: 3px;
  }
  :root[data-theme="light"] {
    --ink: #eef3f1; --panel: #ffffff; --panel-2: #f4f8f7;
    --grid: #d7e2df; --grid-strong: #c3d3cf; --paper: #10262c;
    --dim: #4c6b71; --dim-2: #7d9ba1; --hair: #d2ddda;
  }
  * { box-sizing: border-box; }
  html, body {
    margin: 0; padding: 0; background: var(--ink); color: var(--paper);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    -webkit-font-smoothing: antialiased;
  }
  .mono {
    font-family: ui-monospace, "SF Mono", "Cascadia Mono", "Roboto Mono", Menlo, Consolas, monospace;
    font-variant-numeric: tabular-nums;
  }
  .label { text-transform: uppercase; letter-spacing: 0.09em; font-size: 11px; color: var(--dim); font-weight: 600; }
  a { color: inherit; }
  a.back { text-decoration: none; color: var(--dim); font-size: 12px; }
  a.back:hover { color: var(--paper); }

  header {
    display: flex; align-items: center; gap: 22px; flex-wrap: wrap;
    padding: 16px 24px; border-bottom: 1px solid var(--hair); background: var(--panel-2);
    position: sticky; top: 0; z-index: 30;
  }
  .brand { display: flex; flex-direction: column; gap: 2px; margin-right: auto; }
  .brand .title { font-size: 17px; font-weight: 700; letter-spacing: 0.02em; }
  .brand .sub { font-size: 11.5px; color: var(--dim); }
  .meta { display: flex; gap: 22px; flex-wrap: wrap; }
  .meta .item { display: flex; flex-direction: column; gap: 2px; }
  .meta .item .v { font-size: 13px; }
  .meta .item .v.warn { color: var(--mark); }

  section { border-bottom: 1px solid var(--hair); }
  .section-head {
    display: flex; align-items: baseline; justify-content: space-between;
    padding: 16px 24px 0;
  }
  .section-title { font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; }

  .chart-wrap { background: var(--panel-2); position: relative; height: 62vh; min-height: 420px; }
  #courseChart { width: 100%; height: 100%; display: block; }
  .legend {
    position: absolute; top: 14px; left: 14px; display: flex; flex-direction: column; gap: 6px;
    background: rgba(10, 26, 32, 0.72); backdrop-filter: blur(4px);
    padding: 10px 12px; border-radius: var(--radius); border: 1px solid var(--hair); font-size: 11px;
  }
  :root[data-theme="light"] .legend { background: rgba(255,255,255,0.82); }
  .legend .row { display: flex; align-items: center; gap: 8px; }
  .legend .sw { width: 12px; height: 12px; border-radius: 50%; flex: none; }
  .legend .ln { width: 16px; height: 3px; border-radius: 2px; flex: none; }
  .scale { position: absolute; bottom: 16px; right: 14px; display: flex; align-items: center; gap: 6px; font-size: 10px; color: var(--dim); }
  .scale .bar { height: 2px; background: var(--dim); }
  .marks-legend {
    top: auto; bottom: 14px; left: 14px; max-height: 46%; overflow-y: auto;
    display: grid; grid-template-columns: auto 1fr; gap: 4px 10px; font-size: 10.5px;
  }
  .marks-legend .mnum {
    display: inline-flex; align-items: center; justify-content: center; width: 16px; height: 16px;
    border-radius: 50%; background: var(--mark); color: #201404; font-weight: 700; font-size: 9px;
  }
  .marks-legend .mname { color: var(--paper); align-self: center; }
  .tooltip {
    position: absolute; pointer-events: none; background: var(--panel);
    border: 1px solid var(--grid-strong); border-radius: var(--radius);
    padding: 8px 10px; font-size: 11px; line-height: 1.5; white-space: nowrap;
    box-shadow: 0 4px 16px rgba(0,0,0,0.35); opacity: 0; transition: opacity 0.08s; z-index: 20;
  }
  .tooltip .t-title { font-weight: 700; margin-bottom: 2px; }
  .tooltip.show { opacity: 1; }

  .stats {
    display: grid; grid-template-columns: repeat(5, 1fr); gap: 1px; background: var(--hair);
    margin: 14px 24px 0; border: 1px solid var(--hair); border-radius: var(--radius); overflow: hidden;
  }
  @media (max-width: 900px) { .stats { grid-template-columns: repeat(3, 1fr); } }
  .stat { background: var(--panel); padding: 12px 14px; }
  .stat .num { font-size: 20px; font-weight: 700; }
  .stat .num .unit { font-size: 11px; color: var(--dim); font-weight: 600; margin-left: 3px; }
  .log-wrap { margin: 4px 24px 20px; }
  .log-head { padding: 12px 0 8px; display: flex; align-items: baseline; justify-content: space-between; }
  .log { border: 1px solid var(--hair); border-radius: var(--radius); max-height: 420px; overflow-y: auto; }
  .maneuver-row {
    display: grid; grid-template-columns: 20px 62px 1fr 56px 44px; gap: 10px; align-items: center;
    padding: 8px 14px; border-top: 1px solid var(--hair); font-size: 12px; cursor: pointer;
  }
  .maneuver-row:first-child { border-top: none; }
  .maneuver-row:hover, .maneuver-row.hi { background: var(--panel-2); }
  .maneuver-row.head {
    cursor: default; padding: 10px 14px; font-size: 13px; text-transform: uppercase;
    letter-spacing: 0.07em; color: var(--paper); font-weight: 700;
    position: sticky; top: 0; background: var(--panel); z-index: 2;
    border-bottom: 1px solid var(--hair);
  }
  .maneuver-row.head:hover { background: var(--panel); }
  .m-deg { text-align: right; }
  .glyph { width: 10px; height: 10px; justify-self: center; }
  .glyph.diamond { transform: rotate(45deg); border-radius: 2px; background: var(--maneuver); }
  .glyph.star { border-radius: 50%; background: var(--mark); }
  .m-type { text-transform: capitalize; font-weight: 600; }
  .m-detail { color: var(--dim); font-size: 11px; }
  .m-dur { color: var(--dim); }

  footer {
    padding: 12px 24px; background: var(--panel-2);
    font-size: 10.5px; color: var(--dim-2); display: flex; gap: 18px; flex-wrap: wrap;
  }
  ::-webkit-scrollbar { width: 9px; height: 9px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--hair); border-radius: 5px; }
</style>

<header>
  <a class="back" href="/">&larr; All races</a>
  <div class="brand">
    <div class="title">__TITLE__</div>
    <div class="sub">__SERIES__ &middot; __BOAT__ &middot; Vakaros Analysis</div>
  </div>
  <div class="meta" id="metaPanel"></div>
</header>

<section id="course-section">
  <div class="section-head"><span class="section-title">Course Plot</span></div>
  <div class="chart-wrap">
    <svg id="courseChart" xmlns="http://www.w3.org/2000/svg"></svg>
    <div class="legend" id="legend"></div>
    <div class="legend marks-legend" id="marksLegend"></div>
    <div class="scale" id="scaleBar"></div>
    <div class="tooltip mono" id="courseTooltip"></div>
  </div>
</section>

<section id="maneuver-section">
  <div class="section-head"><span class="section-title">Maneuver Analysis</span></div>
  <div class="stats" id="stats"></div>
  <div class="log-wrap">
    <div class="log-head"><span class="label">Maneuver log</span><span class="label" id="logCount"></span></div>
    <div class="log" id="log"></div>
  </div>
</section>

<footer>
  <span>Course: GPS position from Vakaros track export, resampled to 1 Hz, decimated 1:3</span>
  <span>Maneuvers: heading-change episodes, min 45&deg; turn, min 1.5 kn &mdash; not classified tack/gybe (Vakaros logs no wind angle)</span>
  <span>Roundings: local minimum in distance to a known club mark, within 150m</span>
</footer>

<script id="course-data" type="application/json">__COURSE_DATA__</script>
<script>
(function () {
  "use strict";
  const COURSE = JSON.parse(document.getElementById("course-data").textContent);
  const svgNS = "http://www.w3.org/2000/svg";

  function fmtLocalTs(ts) {
    // Vakaros CSV timestamps carry an explicit UTC offset already resolved
    // to true UTC at build time (build_vakaros_db.py); display in ADT (UTC-3).
    const t = new Date(new Date(ts.replace(" ", "T") + "Z").getTime() - 3 * 3600 * 1000);
    return String(t.getUTCHours()).padStart(2, "0") + ":" +
           String(t.getUTCMinutes()).padStart(2, "0") + ":" +
           String(t.getUTCSeconds()).padStart(2, "0");
  }

  function buildMeta() {
    const el = document.getElementById("metaPanel");
    const durMin = Math.round((new Date(COURSE.utc_end) - new Date(COURSE.utc_start)) / 60000);
    el.innerHTML = `
      <div class="item"><span class="label">Local start</span><span class="v mono">${fmtLocalTs(COURSE.utc_start)} ADT</span></div>
      <div class="item"><span class="label">Logged span</span><span class="v mono">${durMin} min</span></div>
    `;
  }

  const chart = document.getElementById("courseChart");
  const tooltip = document.getElementById("courseTooltip");
  const chartWrap = chart.parentElement;
  let markerEls = [];
  let hiRowEl = null;

  const track = COURSE.track;

  function speedColor(kn, minKn, maxKn) {
    const t = maxKn > minKn ? Math.max(0, Math.min(1, (kn - minKn) / (maxKn - minKn))) : 0.5;
    const stops = [[0.00,[64,110,168]],[0.35,[66,150,150]],[0.65,[219,168,68]],[1.00,[224,96,68]]];
    let a = stops[0], b = stops[stops.length - 1];
    for (let i = 0; i < stops.length - 1; i++) {
      if (t >= stops[i][0] && t <= stops[i + 1][0]) { a = stops[i]; b = stops[i + 1]; break; }
    }
    const span = b[0] - a[0] || 1;
    const lt = (t - a[0]) / span;
    const c = a[1].map((v, i) => Math.round(v + (b[1][i] - v) * lt));
    return `rgb(${c[0]},${c[1]},${c[2]})`;
  }

  function buildLegend() {
    document.getElementById("legend").innerHTML = `
      <div class="row"><span class="ln" style="background:${speedColor(0,0,1)}"></span>slow</div>
      <div class="row"><span class="ln" style="background:${speedColor(1,0,1)}"></span>fast (SOG)</div>
      <div class="row"><span class="sw" style="background:var(--maneuver);border-radius:2px;transform:rotate(45deg)"></span>maneuver</div>
      <div class="row"><span class="sw" style="background:var(--mark)"></span>rounding / mark</div>
    `;
  }

  function buildMarksLegend() {
    document.getElementById("marksLegend").innerHTML = COURSE.waypoints.map(wp =>
      `<span class="mnum">${wp.id}</span><span class="mname">${wp.name}</span>`
    ).join("");
  }

  function statBlock(num, unit, label) {
    return `<div class="stat"><div class="num">${num}<span class="unit">${unit}</span></div><div class="label">${label}</div></div>`;
  }
  function avgOf(arr) {
    const v = arr.filter(x => x !== null && x !== undefined);
    if (!v.length) return null;
    return v.reduce((a, b) => a + b, 0) / v.length;
  }

  function buildStats() {
    const el = document.getElementById("stats");
    const mans = COURSE.maneuvers.filter(m => m.type === "maneuver");
    const roundings = COURSE.maneuvers.filter(m => m.type === "rounding");
    const avgLoss = avgOf(mans.map(m => m.speed_loss_pct));
    const avgDur = avgOf(mans.map(m => m.duration_s));
    const maxSog = Math.max(...track.map(p => p[4] || 0));
    el.innerHTML =
      statBlock(mans.length, "", "Maneuvers") + statBlock(roundings.length, "", "Roundings") +
      statBlock(maxSog.toFixed(1), "kn", "Max speed") +
      statBlock(avgDur !== null ? avgDur.toFixed(0) : "&mdash;", "s", "Avg duration") +
      statBlock(avgLoss !== null ? avgLoss.toFixed(0) : "&mdash;", "%", "Avg speed loss");
  }

  function typeLabel(m) {
    if (m.type === "rounding") return `Rounding (${m.mark_name})`;
    return "Maneuver";
  }
  function glyphFor(m) {
    if (m.type === "rounding") return `<span class="glyph star"></span>`;
    return `<span class="glyph diamond"></span>`;
  }

  function buildLog() {
    const log = document.getElementById("log");
    const mans = COURSE.maneuvers;
    document.getElementById("logCount").textContent = mans.length + " events";
    log.innerHTML = "";

    const head = document.createElement("div");
    head.className = "maneuver-row head";
    head.innerHTML = `<span></span><span>Time</span><span>Event</span>` +
      `<span class="m-deg">Turn</span><span class="m-deg">Dur</span>`;
    log.appendChild(head);

    mans.forEach((m, i) => {
      const row = document.createElement("div");
      row.className = "maneuver-row";
      row.tabIndex = 0;
      const hhmmss = fmtLocalTs(m.start_utc);
      let detail = "";
      if (m.speed_loss_pct !== null && m.speed_loss_pct !== undefined) detail += `-${m.speed_loss_pct}% spd`;
      if (m.distance_to_mark !== null && m.distance_to_mark !== undefined) detail += (detail ? " &middot; " : "") + `${m.distance_to_mark}m to mark`;
      row.innerHTML = `${glyphFor(m)}<span class="mono m-dur">${hhmmss}</span>` +
        `<span><span class="m-type">${typeLabel(m)}</span><br><span class="m-detail">${detail}</span></span>` +
        `<span class="mono m-deg">${m.heading_change !== null && m.heading_change !== undefined ? Math.abs(m.heading_change) + "&deg;" : ""}</span>` +
        `<span class="mono m-dur m-deg">${m.duration_s !== null ? m.duration_s.toFixed(0) + "s" : ""}</span>`;
      row.addEventListener("mouseenter", () => highlightManeuver(i, row));
      row.addEventListener("focus", () => highlightManeuver(i, row));
      log.appendChild(row);
    });
  }

  function highlightManeuver(i, row) {
    if (hiRowEl) hiRowEl.classList.remove("hi");
    hiRowEl = row;
    row.classList.add("hi");
    markerEls.forEach((el, j) => el.setAttribute("stroke-width", j === i ? "2.5" : "1"));
    if (markerEls[i]) markerEls[i].parentNode.appendChild(markerEls[i]);
  }

  function drawChart() {
    const xs = track.map(p => p[1]).concat(COURSE.waypoints.map(w => w.x));
    const ys = track.map(p => p[2]).concat(COURSE.waypoints.map(w => w.y));
    const minX = Math.min(...xs), maxX = Math.max(...xs);
    const minY = Math.min(...ys), maxY = Math.max(...ys);
    const padFrac = 0.08;
    const spanX = (maxX - minX) || 100, spanY = (maxY - minY) || 100;
    const padX = spanX * padFrac, padY = spanY * padFrac;
    const rect = chartWrap.getBoundingClientRect();
    const W = Math.max(320, rect.width), H = Math.max(320, rect.height);
    const dataW = spanX + 2 * padX, dataH = spanY + 2 * padY;
    const scale = Math.min(W / dataW, H / dataH);
    const offX = (W - dataW * scale) / 2, offY = (H - dataH * scale) / 2;
    function sx(x) { return offX + (x - (minX - padX)) * scale; }
    function sy(y) { return H - (offY + (y - (minY - padY)) * scale); }

    chart.setAttribute("viewBox", `0 0 ${W} ${H}`);
    chart.innerHTML = "";

    const rawStep = dataW / 6;
    const mag = Math.pow(10, Math.floor(Math.log10(rawStep)));
    const steps = [1, 2, 5, 10].map(m => m * mag);
    const step = steps.reduce((a, b) => Math.abs(b - rawStep) < Math.abs(a - rawStep) ? b : a);

    const gridGroup = document.createElementNS(svgNS, "g");
    for (let gx = Math.ceil((minX - padX) / step) * step; gx <= maxX + padX; gx += step) {
      const line = document.createElementNS(svgNS, "line");
      line.setAttribute("x1", sx(gx)); line.setAttribute("x2", sx(gx));
      line.setAttribute("y1", 0); line.setAttribute("y2", H);
      line.setAttribute("stroke", "var(--grid)"); line.setAttribute("stroke-width", "1");
      gridGroup.appendChild(line);
    }
    for (let gy = Math.ceil((minY - padY) / step) * step; gy <= maxY + padY; gy += step) {
      const line = document.createElementNS(svgNS, "line");
      line.setAttribute("y1", sy(gy)); line.setAttribute("y2", sy(gy));
      line.setAttribute("x1", 0); line.setAttribute("x2", W);
      line.setAttribute("stroke", "var(--grid)"); line.setAttribute("stroke-width", "1");
      gridGroup.appendChild(line);
    }
    chart.appendChild(gridGroup);

    const speeds = track.map(p => p[4]).filter(v => v !== null && v !== undefined);
    const minS = Math.min(...speeds), maxS = Math.max(...speeds);
    const N_BUCKET = 10;
    function bucketOf(v) {
      if (v === null || v === undefined) return -1;
      const t = maxS > minS ? (v - minS) / (maxS - minS) : 0;
      return Math.min(N_BUCKET - 1, Math.floor(t * N_BUCKET));
    }
    let curBucket = null, curPath = [];
    const trackGroup = document.createElementNS(svgNS, "g");
    trackGroup.setAttribute("fill", "none");
    trackGroup.setAttribute("stroke-linecap", "round");
    trackGroup.setAttribute("stroke-linejoin", "round");
    function flushPath() {
      if (curPath.length < 2 || curBucket === null) { curPath = []; return; }
      const d = curPath.map((p, i) => `${i === 0 ? "M" : "L"}${sx(p[1]).toFixed(1)},${sy(p[2]).toFixed(1)}`).join(" ");
      const path = document.createElementNS(svgNS, "path");
      path.setAttribute("d", d);
      const midT = (curBucket + 0.5) / N_BUCKET;
      path.setAttribute("stroke", speedColor(midT, 0, 1));
      path.setAttribute("stroke-width", "2.25");
      trackGroup.appendChild(path);
      curPath = [];
    }
    track.forEach((p) => {
      const b = bucketOf(p[4]);
      if (b !== curBucket) {
        if (curPath.length) curPath.push(p);
        flushPath();
        curBucket = b;
        curPath = [p];
      } else { curPath.push(p); }
    });
    flushPath();
    chart.appendChild(trackGroup);

    const hoverGroup = document.createElementNS(svgNS, "g");
    const HOVER_STEP = Math.max(1, Math.floor(track.length / 600));
    for (let i = 0; i < track.length; i += HOVER_STEP) {
      const p = track[i];
      const c = document.createElementNS(svgNS, "circle");
      c.setAttribute("cx", sx(p[1])); c.setAttribute("cy", sy(p[2]));
      c.setAttribute("r", "7"); c.setAttribute("fill", "transparent");
      c.addEventListener("mouseenter", (ev) => showTooltip(ev, p));
      c.addEventListener("mouseleave", hideTooltip);
      hoverGroup.appendChild(c);
    }
    chart.appendChild(hoverGroup);

    COURSE.waypoints.forEach(wp => {
      const g = document.createElementNS(svgNS, "g");
      const cx = sx(wp.x), cy = sy(wp.y);
      const r = 10;
      const c = document.createElementNS(svgNS, "circle");
      c.setAttribute("cx", cx); c.setAttribute("cy", cy); c.setAttribute("r", r);
      c.setAttribute("fill", "var(--mark)");
      c.setAttribute("stroke", "var(--ink)"); c.setAttribute("stroke-width", "1.5");
      g.appendChild(c);
      const label = document.createElementNS(svgNS, "text");
      label.setAttribute("x", cx); label.setAttribute("y", cy);
      label.setAttribute("fill", "#201404"); label.setAttribute("font-size", wp.id.length > 1 ? "9.5" : "11");
      label.setAttribute("font-weight", "700"); label.setAttribute("text-anchor", "middle");
      label.setAttribute("dominant-baseline", "central");
      label.textContent = wp.id;
      g.appendChild(label);
      g.style.cursor = "pointer";
      g.addEventListener("mouseenter", (ev) => showTooltip(ev, null, `Mark ${wp.id}: ${wp.name}`));
      g.addEventListener("mouseleave", hideTooltip);
      chart.appendChild(g);
    });

    markerEls = [];
    COURSE.maneuvers.forEach((m) => {
      let el;
      const cx = sx(m.x), cy = sy(m.y);
      if (m.type === "rounding") {
        el = document.createElementNS(svgNS, "circle");
        el.setAttribute("cx", cx); el.setAttribute("cy", cy); el.setAttribute("r", "6");
        el.setAttribute("fill", "var(--mark)");
      } else {
        el = document.createElementNS(svgNS, "rect");
        const size = 9;
        el.setAttribute("x", cx - size / 2); el.setAttribute("y", cy - size / 2);
        el.setAttribute("width", size); el.setAttribute("height", size);
        el.setAttribute("transform", `rotate(45 ${cx} ${cy})`);
        el.setAttribute("fill", "var(--maneuver)");
      }
      el.setAttribute("stroke", "var(--ink)"); el.setAttribute("stroke-width", "1");
      el.style.cursor = "pointer";
      el.addEventListener("mouseenter", (ev) => showTooltip(ev, null, maneuverTooltip(m)));
      el.addEventListener("mouseleave", hideTooltip);
      chart.appendChild(el);
      markerEls.push(el);
    });

    const scaleEl = document.getElementById("scaleBar");
    const barPx = step * scale;
    scaleEl.innerHTML = `<span class="bar" style="width:${barPx}px"></span><span>${step >= 1000 ? (step/1000)+" km" : step+" m"}</span>`;
  }

  function maneuverTooltip(m) {
    let s = `<div class="t-title">${typeLabel(m)}</div>`;
    if (m.heading_before !== null && m.heading_before !== undefined) s += `hdg ${m.heading_before}&deg; &rarr; ${m.heading_after}&deg;<br>`;
    if (m.speed_before !== null && m.speed_before !== undefined) s += `spd ${m.speed_before}`;
    if (m.speed_min !== null && m.speed_min !== undefined) s += ` &rarr; ${m.speed_min} kn`;
    if (m.speed_loss_pct !== null && m.speed_loss_pct !== undefined) s += ` (-${m.speed_loss_pct}%)`;
    if (m.distance_to_mark !== null && m.distance_to_mark !== undefined) s += `<br>${m.distance_to_mark} m to mark`;
    return s;
  }
  function showTooltip(ev, trackPoint, htmlContent) {
    const wrapRect = chartWrap.getBoundingClientRect();
    let content = htmlContent;
    if (trackPoint) {
      const [elapsed, x, y, hdg, sog, heel, trimAngle] = trackPoint;
      content = `<div class="t-title">Track</div>` +
        `hdg ${hdg}&deg; &middot; SOG ${sog} kn<br>heel ${heel}&deg; &middot; trim ${trimAngle}&deg;`;
    }
    tooltip.innerHTML = content;
    tooltip.classList.add("show");
    tooltip.style.left = (ev.clientX - wrapRect.left + 14) + "px";
    tooltip.style.top = (ev.clientY - wrapRect.top + 14) + "px";
  }
  function hideTooltip() { tooltip.classList.remove("show"); }

  buildLegend(); buildMarksLegend(); buildStats(); buildLog(); drawChart();
  buildMeta();
  window.addEventListener("resize", drawChart);
})();
</script>
"""


def render_vakaros_page(race_meta):
    """Returns the Vakaros Analysis page HTML for one race, or None if it
    has no registered/usable Vakaros data."""
    course = build_vakaros_db.build_for_race(race_meta)
    if course is None:
        return None

    title = f"{race_meta['race_date']} {race_meta['series']}"
    html = (PAGE_TEMPLATE
            .replace("__TITLE__", title)
            .replace("__SERIES__", race_meta["series"])
            .replace("__BOAT__", race_meta.get("boat", "Critical Mass"))
            .replace("__COURSE_DATA__", json.dumps(course, separators=(",", ":"))))
    return html


def render_all():
    from race_registry import load_registry
    registered_ids = {r["race_id"] for r in vakaros_registry.load_registry()["races"]}

    VAKAROS_DIR.mkdir(exist_ok=True)
    written = []
    for race in load_registry()["races"]:
        if race["id"] not in registered_ids:
            continue
        html = render_vakaros_page(race)
        if html is None:
            print(f"# WARNING: race {race['id']} ({race['race_date']}) has no usable Vakaros data, skipping page")
            continue
        out_path = VAKAROS_DIR / f"{race['id']}.html"
        out_path.write_text(html)
        written.append(race["id"])
        print(f"# Wrote {out_path} ({out_path.stat().st_size/1024:.0f} KB)")
    return written


if __name__ == "__main__":
    render_all()
